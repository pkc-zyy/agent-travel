"""记忆 API：查看 / 新增 / 删除用户的长期记忆。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.memory.longterm import get_long_term_memory
from app.models import MemoryCreate, MemoryDelete

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
async def list_memory(user_id: str = "default", kind: str | None = None):
    items = await get_long_term_memory().list_items(user_id, kind)
    return [it.to_dict() for it in items]


@router.post("")
async def add_memory(body: MemoryCreate):
    item = await get_long_term_memory().add(body.user_id, body.kind, body.content, body.source)
    if item is None:
        return {"ok": False, "reason": "内容为空或重复"}
    return {"ok": True, "memory": item.to_dict()}


@router.delete("")
async def delete_memory(body: MemoryDelete):
    n = await get_long_term_memory().delete(body.memory_ids)
    return {"ok": True, "deleted": n}
