"""知识库 API：用户上传/管理资料（txt/md 或直接粘贴文本），实时进入 RAG 双索引。"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_session
from app.db.models import KnowledgeDoc
from app.rag.knowledge import chunk_text, get_knowledge_base

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".log"}


class IngestRequest(BaseModel):
    title: str = Field("", max_length=300)
    text: str = Field(..., min_length=1, max_length=200_000)
    user_id: str = "default"


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc).lstrip("\ufeff")  # 去掉 BOM
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="ignore").lstrip("\ufeff")


async def _add_document(
    user_id: str,
    title: str,
    text: str,
    filename: str,
    session: AsyncSession,
) -> dict:
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="内容为空")
    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="无法解析出有效文本")

    doc = KnowledgeDoc(
        user_id=user_id,
        title=(title or filename or "未命名资料").strip()[:300],
        filename=filename,
        char_count=len(text),
        chunk_count=len(chunks),
    )
    session.add(doc)
    await session.flush()  # 拿到自增 id

    # 落盘（供重启后重建索引）
    kb = get_knowledge_base()
    uploads_dir = kb.settings.knowledge_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (uploads_dir / f"{doc.id}.txt").write_text(text, encoding="utf-8")
    (uploads_dir / f"{doc.id}.json").write_text(
        json.dumps({"title": doc.title, "filename": filename}, ensure_ascii=False),
        encoding="utf-8",
    )

    # 实时写入向量 + BM25 双索引
    await kb.add_document(doc.id, doc.title, text, filename)

    await session.commit()
    await session.refresh(doc)
    return doc.to_dict()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    user_id: str = Form("default"),
    session: AsyncSession = Depends(get_session),
):
    """上传文本文件（.txt / .md 等）进入知识库。"""
    filename = file.filename or "upload.txt"
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix and suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"暂不支持 {suffix} 类型，请上传 {', '.join(sorted(_ALLOWED_SUFFIXES))} 文件，或使用「粘贴文本」",
        )
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(status_code=400, detail="文件过大（上限 5MB）")
    text = _decode(data)
    return await _add_document(user_id, title, text, filename, session)


@router.post("/ingest")
async def ingest_text(body: IngestRequest, session: AsyncSession = Depends(get_session)):
    """直接粘贴文本进入知识库。"""
    return await _add_document(body.user_id, body.title, body.text, "(粘贴文本)", session)


@router.get("/documents")
async def list_documents(user_id: str = "default", session: AsyncSession = Depends(get_session)):
    rows = (
        (
            await session.execute(
                select(KnowledgeDoc)
                .where(KnowledgeDoc.user_id == user_id)
                .order_by(KnowledgeDoc.created_at.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    return [r.to_dict() for r in rows]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(KnowledgeDoc, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="资料不存在")

    # 从索引移除
    kb = get_knowledge_base()
    removed = await kb.remove_document(doc.id)

    # 删除落盘文件
    uploads_dir = kb.settings.knowledge_dir / "uploads"
    for f in (uploads_dir / f"{doc.id}.txt", uploads_dir / f"{doc.id}.json"):
        if f.exists():
            f.unlink()

    await session.delete(doc)
    await session.commit()
    return {"ok": True, "id": doc_id, "removed_chunks": removed}
