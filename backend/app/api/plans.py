"""行程 API：查看 / 评分 / 删除已保存的旅行方案。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.db.models import Trip
from app.models import TripUpdate

router = APIRouter(prefix="/plans", tags=["plans"])


@router.get("")
async def list_plans(user_id: str = "default", session: AsyncSession = Depends(get_session)):
    rows = (
        (await session.execute(
            select(Trip).where(Trip.user_id == user_id).order_by(Trip.created_at.desc()).limit(100)
        ))
        .scalars()
        .all()
    )
    return [r.to_dict() for r in rows]


@router.get("/{trip_id}")
async def get_plan(trip_id: int, session: AsyncSession = Depends(get_session)):
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="行程不存在")
    data = trip.to_dict()
    try:
        data["plan"] = json.loads(trip.plan_json or "{}")
    except json.JSONDecodeError:
        data["plan"] = {}
    data["markdown"] = trip.markdown
    return data


@router.put("/{trip_id}")
async def update_plan(trip_id: int, body: TripUpdate, session: AsyncSession = Depends(get_session)):
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="行程不存在")
    if body.title is not None:
        trip.title = body.title
    if body.rating is not None:
        trip.rating = body.rating
    await session.commit()
    await session.refresh(trip)
    return trip.to_dict()


@router.delete("/{trip_id}")
async def delete_plan(trip_id: int, session: AsyncSession = Depends(get_session)):
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="行程不存在")
    await session.delete(trip)
    await session.commit()
    return {"ok": True, "id": trip_id}
