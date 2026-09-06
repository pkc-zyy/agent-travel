"""上下文管理器：按预算组装「系统提示 + 用户画像 + 会话历史 + 长期记忆 + RAG 知识」上下文包。

优先级（预算紧张时先裁剪历史）：
  长期记忆 > RAG 知识 > 会话摘要 > 最近消息
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.memory.longterm import get_long_term_memory
from app.memory.session import get_session_memory
from app.prompts import SYSTEM_PROMPT
from app.rag.knowledge import get_knowledge_base


@dataclass
class ContextPacket:
    system_prompt: str = SYSTEM_PROMPT
    user_profile: str = ""                    # 长期记忆摘要
    history: list[dict] = field(default_factory=list)
    memories: list[dict] = field(default_factory=list)
    knowledge: list[dict] = field(default_factory=list)

    def to_messages(self, user_message: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        if self.user_profile:
            messages.append({"role": "system", "content": f"用户画像（长期记忆）：{self.user_profile}"})
        for m in self.history:
            messages.append(dict(m))
        messages.append({"role": "user", "content": user_message})
        return messages


class ContextManager:
    def __init__(self):
        self.settings = get_settings()

    async def build(self, user_id: str, session_id: str, message: str,
                    with_knowledge: bool = True) -> ContextPacket:
        packet = ContextPacket()
        budget = self.settings.context_max_chars

        # 1) 长期记忆（最高优先级）
        memories = await get_long_term_memory().retrieve(user_id, message)
        packet.memories = memories
        if memories:
            profile = "；".join(m["content"] for m in memories[:4])
            packet.user_profile = profile[:1200]

        # 2) RAG 知识（若查询与旅行相关）
        if with_knowledge:
            kb = get_knowledge_base()
            try:
                docs = await kb.retrieve(message, k=3)
                packet.knowledge = [
                    {"text": d.text[:500], "meta": d.metadata} for d in docs
                ]
            except Exception:
                packet.knowledge = []

        # 3) 会话历史（摘要 + 最近消息，按预算裁剪）
        sm = get_session_memory()
        summary = sm.get_summary(session_id)
        recent = sm.get_recent(session_id)

        history: list[dict] = []
        used = len(packet.user_profile) + sum(len(k["text"]) for k in packet.knowledge)
        if summary:
            history.append({"role": "system", "content": f"历史对话摘要：{summary[:800]}"})
            used += len(summary)
        for m in reversed(recent):
            cost = len(m["content"]) + 12
            if used + cost > budget:
                break
            history.insert(0, m)
            used += cost

        packet.history = history[-self.settings.session_window:]
        return packet


@lru_cache
def get_context_manager() -> ContextManager:
    return ContextManager()
