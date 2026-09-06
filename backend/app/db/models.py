"""ORM 模型：用户、行程、反馈、长期记忆、知识库文档。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Trip(Base):
    """用户旅行方案（行程主表）。"""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    title: Mapped[str] = mapped_column(String(200), default="我的旅行方案")
    request: Mapped[str] = mapped_column(Text, default="")
    cities: Mapped[str] = mapped_column(String(500), default="")      # 逗号分隔
    days: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[str] = mapped_column(String(100), default="")
    plan_json: Mapped[str] = mapped_column(Text, default="{}")        # 结构化方案
    markdown: Mapped[str] = mapped_column(Text, default="")           # 完整 Markdown 版
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    payment_status: Mapped[str] = mapped_column(String(32), default="draft")  # draft | pending_payment | paid
    price: Mapped[float] = mapped_column(Float, default=0.0)          # 订单金额
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "request": self.request,
            "cities": [c.strip() for c in self.cities.split(",") if c.strip()],
            "days": self.days,
            "budget": self.budget,
            "rating": self.rating,
            "payment_status": self.payment_status,
            "price": self.price,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Feedback(Base):
    """用户反馈：形成「规划 → 反馈 → 学习」闭环。"""

    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    trip_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[int] = mapped_column(Integer, default=5)           # 1-5
    comment: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(200), default="")        # 逗号分隔，如 "酒店太贵,路线太赶"
    lessons: Mapped[str] = mapped_column(Text, default="")            # 学习到的改进项
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "trip_id": self.trip_id,
            "rating": self.rating,
            "comment": self.comment,
            "tags": [t.strip() for t in self.tags.split(",") if t.strip()],
            "lessons": self.lessons,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MemoryItem(Base):
    """长期记忆：从对话/反馈中沉淀的用户偏好与事实。"""

    __tablename__ = "memory_items"
    __table_args__ = (UniqueConstraint("user_id", "content", name="uq_memory_content"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    kind: Mapped[str] = mapped_column(String(20), default="preference")  # preference | fact | lesson
    content: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(100), default="")       # chat | feedback
    score: Mapped[float] = mapped_column(Float, default=1.0)           # 记忆强度（可衰减）
    hit_count: Mapped[int] = mapped_column(Integer, default=0)         # 命中次数（强化记忆）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "kind": self.kind,
            "content": self.content,
            "source": self.source,
            "score": self.score,
            "hit_count": self.hit_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class KnowledgeDoc(Base):
    """用户上传到知识库的资料（用于 RAG）。"""

    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    title: Mapped[str] = mapped_column(String(300), default="未命名资料")
    filename: Mapped[str] = mapped_column(String(300), default="")
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "filename": self.filename,
            "char_count": self.char_count,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Order(Base):
    """行程订单：客户发起支付请求 → 管理员人工确认收款。"""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    trip_id: Mapped[int] = mapped_column(Integer, index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="pending_payment")  # pending_payment | paid | cancelled
    payment_method: Mapped[str] = mapped_column(String(64), default="线下转账")
    payment_note: Mapped[str] = mapped_column(Text, default="")       # 支付指引
    operator: Mapped[str] = mapped_column(String(64), default="")     # 人工确认收款的操作人
    operator_note: Mapped[str] = mapped_column(Text, default="")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "trip_id": self.trip_id,
            "amount": self.amount,
            "status": self.status,
            "payment_method": self.payment_method,
            "payment_note": self.payment_note,
            "operator": self.operator,
            "operator_note": self.operator_note,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
