"""反馈 API：提交反馈 → 反馈分析师学习 → 沉淀长期记忆，形成「规划→反馈→学习」闭环。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentContext
from app.agents.feedback_agent import FeedbackAgent
from app.db.database import get_session
from app.db.models import Feedback, MemoryItem, Trip
from app.memory.longterm import get_long_term_memory
from app.models import FeedbackCreate
from app.mcp_server.client import get_mcp_client
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback(
    body: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
):
    """提交反馈：入库 + 触发反馈分析师异步学习（写入长期记忆）。"""
    fb = Feedback(
        user_id=body.user_id,
        trip_id=body.trip_id,
        rating=body.rating,
        comment=body.comment,
        tags=",".join(body.tags),
    )
    session.add(fb)
    await session.flush()

    # 同步更新行程评分
    if body.trip_id:
        trip = await session.get(Trip, body.trip_id)
        if trip:
            trip.rating = body.rating
    await session.commit()
    await session.refresh(fb)

    # 反馈分析师学习（后台任务，不阻塞响应）
    ctx = AgentContext(user_id=body.user_id, mcp=get_mcp_client(), settings=get_settings())
    agent = FeedbackAgent(ctx)

    async def learn():
        try:
            result = await agent.process(body.user_id, body.rating, body.comment, body.tags)
            lessons = result["lessons"]
            # 回写学习到的教训
            async with get_session() as s2:
                row = await s2.get(Feedback, fb.id)
                if row:
                    row.lessons = "\n".join(lessons)
                    await s2.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("反馈学习失败: %s", e)

    import asyncio

    asyncio.create_task(learn())

    return {"feedback": fb.to_dict(), "status": "learning"}


@router.get("")
async def list_feedback(user_id: str = "default", session: AsyncSession = Depends(get_session)):
    rows = (
        (await session.execute(
            select(Feedback).where(Feedback.user_id == user_id).order_by(Feedback.created_at.desc()).limit(100)
        ))
        .scalars()
        .all()
    )
    return [r.to_dict() for r in rows]


@router.get("/learned")
async def learned_lessons(user_id: str = "default", session: AsyncSession = Depends(get_session)):
    """系统从该用户反馈中学到的经验（长期记忆 lessons）。"""
    items = await get_long_term_memory().list_items(user_id, kind="lesson")
    return [it.to_dict() for it in items]


@router.get("/stats")
async def feedback_stats(user_id: str = "default", session: AsyncSession = Depends(get_session)):
    rows = (
        (await session.execute(select(Feedback).where(Feedback.user_id == user_id)))
        .scalars()
        .all()
    )
    if not rows:
        return {"count": 0, "avg_rating": 0, "distribution": {}}
    dist: dict[int, int] = {}
    for r in rows:
        dist[r.rating] = dist.get(r.rating, 0) + 1
    return {
        "count": len(rows),
        "avg_rating": round(sum(r.rating for r in rows) / len(rows), 2),
        "distribution": {str(k): v for k, v in sorted(dist.items())},
    }
