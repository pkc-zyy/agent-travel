"""订单 / 支付 API：客户规划完成后发起支付 → 管理员人工确认收款。

闭环：规划方案 → 提交订单（pending_payment）→ 线下转账 → 管理员人工确认收款（paid）→ 解锁方案。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.db.models import Order, Trip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["orders"])

_ORDER_STATUSES = ("pending_payment", "paid", "cancelled")


class OrderCreate(BaseModel):
    user_id: str = "default"
    trip_id: int
    amount: float | None = None
    payment_method: str = "线下转账"


class OrderConfirm(BaseModel):
    operator: str = Field(..., min_length=1, max_length=64)   # 人工确认收款的操作人
    note: str = ""


def _payment_note(order_id: int, amount: float) -> str:
    return (
        f"订单号：TRAVEL-{order_id:06d}\n"
        f"应付金额：¥{amount:.2f}\n"
        "支付方式：线下转账 / 对公转账 / 扫码支付（演示）\n"
        "收款账户：招商银行 6225 **** **** 8888（演示账户）\n"
        "请务必在转账备注中填写订单号，到账后由工作人员人工确认开通。"
    )


def _trip_price(trip: Trip) -> float:
    try:
        data = json.loads(trip.plan_json or "{}")
        total = (data.get("budget") or {}).get("total_per_person", 0)
        return float(total or 0)
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0.0


@router.post("")
async def create_order(body: OrderCreate, session: AsyncSession = Depends(get_session)):
    """客户发起支付请求（生成待支付订单 + 支付指引）。"""
    trip = await session.get(Trip, body.trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="行程不存在")

    # 一个行程只允许一个有效（未取消）订单
    existing = (
        await session.execute(
            select(Order).where(
                Order.trip_id == body.trip_id, Order.status != "cancelled"
            )
        )
    ).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail=f"该行程已有订单（状态：{existing.status}），订单号 TRAVEL-{existing.id:06d}")

    amount = body.amount if body.amount is not None else _trip_price(trip)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="金额无效，请先在方案中生成预算或手动填写金额")

    order = Order(
        user_id=body.user_id,
        trip_id=body.trip_id,
        amount=round(amount, 2),
        status="pending_payment",
        payment_method=body.payment_method,
    )
    session.add(order)
    await session.flush()  # 拿到订单号
    order.payment_note = _payment_note(order.id, order.amount)

    trip.payment_status = "pending_payment"
    trip.price = order.amount
    await session.commit()
    await session.refresh(order)
    return order.to_dict()


@router.get("")
async def list_orders(
    user_id: str | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Order).order_by(Order.created_at.desc()).limit(200)
    if user_id:
        stmt = stmt.where(Order.user_id == user_id)
    if status and status in _ORDER_STATUSES:
        stmt = stmt.where(Order.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return [r.to_dict() for r in rows]


@router.get("/pending")
async def list_pending_orders(session: AsyncSession = Depends(get_session)):
    """待人工确认收款的订单（管理员视角）。"""
    rows = (
        (
            await session.execute(
                select(Order)
                .where(Order.status == "pending_payment")
                .order_by(Order.created_at.asc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )
    return [r.to_dict() for r in rows]


@router.post("/{order_id}/confirm")
async def confirm_order(order_id: int, body: OrderConfirm, session: AsyncSession = Depends(get_session)):
    """【人工干预】管理员确认收到款项，将订单标记为已支付。"""
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != "pending_payment":
        raise HTTPException(status_code=409, detail=f"订单当前状态为 {order.status}，无法确认收款")

    order.status = "paid"
    order.operator = body.operator
    order.operator_note = body.note
    order.paid_at = datetime.now(timezone.utc)

    trip = await session.get(Trip, order.trip_id)
    if trip:
        trip.payment_status = "paid"
        trip.price = order.amount
    await session.commit()
    await session.refresh(order)
    return order.to_dict()


@router.post("/{order_id}/cancel")
async def cancel_order(order_id: int, session: AsyncSession = Depends(get_session)):
    """取消待支付订单。"""
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != "pending_payment":
        raise HTTPException(status_code=409, detail=f"订单当前状态为 {order.status}，无法取消")

    order.status = "cancelled"
    trip = await session.get(Trip, order.trip_id)
    if trip:
        trip.payment_status = "draft"
    await session.commit()
    await session.refresh(order)
    return order.to_dict()
