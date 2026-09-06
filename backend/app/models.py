"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------- 聊天 ----------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = "default"
    user_id: str = "default"
    stream: bool = True


class ChatResponse(BaseModel):
    session_id: str
    user_id: str
    reply: str                      # Markdown 文本回复
    intent: str
    data: dict[str, Any] | None     # 结构化数据（行程/卡片等）


# ---------- 行程 ----------
class TripCreate(BaseModel):
    user_id: str = "default"
    title: str = "我的旅行方案"


class TripUpdate(BaseModel):
    title: str | None = None
    rating: float | None = Field(None, ge=0, le=5)


# ---------- 反馈 ----------
class FeedbackCreate(BaseModel):
    user_id: str = "default"
    trip_id: int | None = None
    rating: int = Field(..., ge=1, le=5)
    comment: str = ""
    tags: list[str] = []


# ---------- 记忆 ----------
class MemoryCreate(BaseModel):
    user_id: str = "default"
    kind: Literal["preference", "fact", "lesson"] = "preference"
    content: str = Field(..., min_length=1)
    source: str = "manual"


class MemoryDelete(BaseModel):
    memory_ids: list[int]


# ---------- MCP ----------
class MCPToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


class MCPToolResult(BaseModel):
    tool: str
    ok: bool
    data: Any = None
    error: str | None = None
