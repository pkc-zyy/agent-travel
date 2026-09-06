"""Agent 基类与公共类型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.mcp_server.client import TravelMCPClient
from app.memory.context import ContextPacket

# 事件推送：{type, ...} 发给前端 SSE
EmitFn = Callable[[dict], Awaitable[None]]


@dataclass
class TripSpec:
    """行程需求解析结果。"""
    cities: list[str] = field(default_factory=list)
    days: int = 3
    budget: str = ""                      # 如 "人均3000-5000元" / "经济型"
    budget_level: str = "综合"            # 经济 / 舒适 / 豪华 / 综合
    preferences: list[str] = field(default_factory=list)
    travelers: str = ""
    start_date: str = ""
    needs_more_info: str = ""             # 非空表示信息不足，需要追问


@dataclass
class AgentContext:
    user_id: str = "default"
    session_id: str = "default"
    request: str = ""
    packet: ContextPacket | None = None
    mcp: TravelMCPClient | None = None
    settings: Settings | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    """所有专家 Agent 的基类。"""

    name: str = "智能体"
    emoji: str = "🤖"
    role: str = ""

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx

    async def emit(self, status: str, message: str, agent: str | None = None,
                   data: dict | None = None) -> None:
        from app.services.monitor import get_monitor

        get_monitor().record(
            "agent",
            agent or self.name,
            {"status": status, "message": message, **(data or {})},
            session_id=getattr(self.ctx, "session_id", "") if self.ctx else "",
        )
        if self.ctx and self.ctx.extra.get("emit"):
            await self.ctx.extra["emit"](
                {
                    "type": "agent",
                    "agent": agent or self.__class__.__name__,
                    "name": self.name,
                    "emoji": self.emoji,
                    "role": self.role,
                    "status": status,       # running | done | error
                    "message": message,
                    "data": data or {},
                }
            )

    @property
    def mcp(self) -> TravelMCPClient:
        return self.ctx.mcp  # type: ignore[return-value]

    @property
    def settings(self):
        return self.ctx.settings
