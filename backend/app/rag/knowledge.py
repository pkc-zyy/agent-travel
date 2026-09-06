"""旅行知识库：加载语料 → 建立 向量 + BM25 双通道索引 → 混合检索。

语料来源（backend/data/knowledge/）：
  cities/*.md       城市旅行指南
  attractions.json  景点知识条目
  hotels.json       酒店知识条目
  tips.md           通用旅行贴士
  uploads/          用户上传的资料（动态入库，可增删）
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.rag.bm25 import BM25Index
from app.rag.hybrid import HybridRetriever
from app.rag.vector_store import RetrievedDoc, VectorStore

logger = logging.getLogger(__name__)

_UPLOADS_DIRNAME = "uploads"


def chunk_text(text: str, size: int = 500, overlap: int = 60) -> list[str]:
    """将长文本切分为重叠的语义块（优先在句末/段末断开）。"""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = start + size
        chunk = text[start:end]
        # 在句末/换行处断开，避免截断语义
        if end < n:
            cut = -1
            for sep in ("。", "！", "？", "\n", "；", "，", " "):
                pos = chunk.rfind(sep)
                if pos > size * 0.5:
                    cut = pos + 1
                    break
            if cut > 0:
                end = start + cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


class KnowledgeBase:
    def __init__(self):
        self.settings = get_settings()
        self.vector_store = VectorStore("travel_knowledge", str(self.settings.vector_dir))
        self.bm25 = BM25Index()
        self.retriever = HybridRetriever(self.vector_store, self.bm25)
        self._docs: list[dict] = []
        self._ready = False
        self._sig_path = self.settings.vector_dir / "travel_knowledge.sig"

    # ---------- 嵌入源签名（驱动自动重建） ----------
    @staticmethod
    def _sig_key(sig: tuple[str, str]) -> str:
        return f"{sig[0]}:{sig[1]}"

    def _stored_signature(self) -> str:
        try:
            if self._sig_path.exists():
                return self._sig_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return ""

    def _save_signature(self, sig: tuple[str, str]) -> None:
        try:
            self._sig_path.write_text(self._sig_key(sig), encoding="utf-8")
        except Exception:
            pass

    async def _clear_index(self) -> None:
        await asyncio.to_thread(self.vector_store.clear)
        await asyncio.to_thread(self.bm25.clear)

    # ---------- 语料加载 ----------
    def _load_corpus(self) -> list[dict]:
        docs: list[dict] = []
        kdir: Path = self.settings.knowledge_dir

        # 1) 城市指南 markdown
        for md in sorted((kdir / "cities").glob("*.md")):
            text = md.read_text(encoding="utf-8").strip()
            if text:
                docs.append(
                    {"id": f"guide-{md.stem}", "text": text, "meta": {"kind": "guide", "city": md.stem}}
                )

        # 2) 景点知识
        attr_file = kdir / "attractions.json"
        if attr_file.exists():
            for i, item in enumerate(json.loads(attr_file.read_text(encoding="utf-8"))):
                text = f"{item['name']}（{item['city']}）：{item['desc']} 门票约{item['price']}元，建议游玩{item['duration']}。"
                docs.append(
                    {
                        "id": f"attr-{i}",
                        "text": text,
                        "meta": {
                            "kind": "attraction",
                            "city": item["city"],
                            "name": item["name"],
                            "price": item.get("price", 0),
                            "tags": item.get("tags", []),
                        },
                    }
                )

        # 3) 酒店知识
        hotel_file = kdir / "hotels.json"
        if hotel_file.exists():
            for i, item in enumerate(json.loads(hotel_file.read_text(encoding="utf-8"))):
                text = f"{item['name']}（{item['city']}）：{item['desc']} 参考价约{item['price']}元/晚，评分{item['rating']}。"
                docs.append(
                    {
                        "id": f"hotel-{i}",
                        "text": text,
                        "meta": {
                            "kind": "hotel",
                            "city": item["city"],
                            "name": item["name"],
                            "price": item.get("price", 0),
                            "rating": item.get("rating", 0),
                            "tags": item.get("tags", []),
                        },
                    }
                )

        # 4) 通用贴士
        tips_file = kdir / "tips.md"
        if tips_file.exists():
            text = tips_file.read_text(encoding="utf-8").strip()
            if text:
                docs.append({"id": "guide-tips", "text": text, "meta": {"kind": "tips", "city": ""}})

        # 5) 用户上传的资料
        uploads_dir = kdir / _UPLOADS_DIRNAME
        if uploads_dir.exists():
            for txt in sorted(uploads_dir.glob("*.txt")):
                try:
                    raw = txt.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    raw = txt.read_text(encoding="gbk", errors="ignore")
                raw = raw.strip()
                if not raw:
                    continue
                meta_file = txt.with_suffix(".json")
                meta = {}
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        meta = {}
                try:
                    doc_id = int(txt.stem)
                except ValueError:
                    doc_id = txt.stem
                title = meta.get("title") or meta.get("filename") or txt.stem
                filename = meta.get("filename") or txt.name
                for i, piece in enumerate(chunk_text(raw)):
                    docs.append(
                        {
                            "id": f"upload-{doc_id}-{i}",
                            "text": piece,
                            "meta": {
                                "kind": "upload",
                                "city": "",
                                "doc_id": doc_id,
                                "title": title,
                                "filename": filename,
                            },
                        }
                    )

        return docs

    # ---------- 索引构建 ----------
    async def build(self, force: bool = False) -> dict:
        """构建双通道索引（幂等）；嵌入源切换时自动清空重建。"""
        provider = self.vector_store.provider
        configured = provider.configured_signature()          # 配置意图
        stored = self._stored_signature()                     # 上次构建的配置意图

        if self._ready and not force and stored == self._sig_key(configured):
            return {"status": "ready", "docs": len(self._docs), "embedding": provider.mode}

        # 激活实际可用的嵌入模式（API 不可用则回退本地哈希）
        if configured[0] == "api" and provider.probe_api():
            provider.activate("api")
        else:
            provider.activate("local")

        docs = self._load_corpus()
        ids = [d["id"] for d in docs]
        texts = [d["text"] for d in docs]
        metas = [d["meta"] for d in docs]

        # 配置变化或强制 → 清空旧索引重建（避免维度漂移）
        if stored != self._sig_key(configured) or force:
            await self._clear_index()
            logger.info("嵌入源切换（%s → %s），重建知识库索引", stored or "无", self._sig_key(configured))

        if not ids:
            self._save_signature(configured)
            self._docs = docs
            self._ready = True
            return {"status": "empty", "docs": 0, "embedding": provider.mode}

        try:
            await asyncio.to_thread(self.vector_store.add, ids, texts, metas)
        except Exception as e:  # API 嵌入失败（非 probe 阶段）→ 降级本地哈希重建
            logger.warning("API 嵌入失败，降级本地哈希重建: %s", e)
            provider.activate("local")
            await self._clear_index()
            await asyncio.to_thread(self.vector_store.add, ids, texts, metas)

        await asyncio.to_thread(self.bm25.add, ids, texts, metas)

        self._docs = docs
        self._ready = True
        self._save_signature(configured)
        logger.info("知识库索引构建完成：%d 篇文档（嵌入：%s）", len(docs), provider.mode)
        return {"status": "built", "docs": len(docs), "embedding": provider.mode}

    async def ensure_index(self) -> None:
        """运行中检测嵌入源配置变化（如切换 Key/模型），变化则重建。"""
        if not self._ready:
            await self.build()
            return
        provider = self.vector_store.provider
        configured = self._sig_key(provider.configured_signature())
        if configured != self._stored_signature():
            self._ready = False
            await self.build()

    # ---------- 检索 ----------
    async def retrieve(self, query: str, k: int | None = None, kind: str | None = None) -> list[RetrievedDoc]:
        await self.ensure_index()
        where = {"kind": kind} if kind else None
        return await self.retriever.retrieve(query, k=k, where=where)

    # ---------- 用户资料动态增删 ----------
    async def add_document(self, doc_id: int, title: str, text: str, filename: str = "") -> int:
        """将用户上传资料分块并写入双索引（立即生效），返回分块数。"""
        await self.ensure_index()
        chunks = chunk_text(text)
        if not chunks:
            return 0
        ids = [f"upload-{doc_id}-{i}" for i in range(len(chunks))]
        metas = [
            {
                "kind": "upload",
                "city": "",
                "doc_id": doc_id,
                "title": title,
                "filename": filename,
            }
            for _ in chunks
        ]
        await asyncio.to_thread(self.vector_store.add, ids, chunks, metas)
        await asyncio.to_thread(self.bm25.add, ids, chunks, metas)
        self._docs = []  # 重置统计缓存
        logger.info("已入库资料 doc_id=%s 分块 %d", doc_id, len(chunks))
        return len(chunks)

    async def remove_document(self, doc_id: int) -> int:
        """从双索引中删除指定资料的全部分块，返回删除的分块数。"""
        await self.ensure_index()
        ids = await asyncio.to_thread(self.vector_store.delete_where, {"doc_id": doc_id})
        if ids:
            await asyncio.to_thread(self.bm25.delete, ids)
        self._docs = []
        logger.info("已移除资料 doc_id=%s 分块 %d", doc_id, len(ids))
        return len(ids)

    def stats(self) -> dict:
        return {
            "ready": self._ready,
            "docs": len(self._docs),
            "vector_backend": self.vector_store.backend,
            "vector_count": self.vector_store.count(),
            "bm25_count": self.bm25.count(),
            "embedding_mode": self.vector_store.provider.mode,
        }


@lru_cache
def get_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase()
