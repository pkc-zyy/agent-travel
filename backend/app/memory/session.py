"""短期会话记忆：按 session 保存消息历史，采用「摘要 + 滑动窗口」策略管理上下文。

- 窗口内消息直接保留；
- 超出窗口的旧消息被压缩为摘要（LLM 就绪时用 LLM 摘要，否则抽取式摘要）；
- 供上下文组装时按预算截取。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.prompts import SUMMARY_SYSTEM
from app.services.llm import get_llm_client


@dataclass
class SessionRecord:
    messages: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    summarized_count: int = 0


class SessionMemory:
    def __init__(self, window: int | None = None):
        self.settings = get_settings()
        self.window = window or self.settings.session_window
        self._sessions: dict[str, SessionRecord] = {}
        self._summary_lock = asyncio.Lock()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        rec = self._sessions.setdefault(session_id, SessionRecord())
        rec.messages.append({"role": role, "content": content})
        if len(rec.messages) > self.window * 2:
            # 异步压缩（不阻塞调用方）
            asyncio.create_task(self._compress(session_id))

    async def _compress(self, session_id: str) -> None:
        async with self._summary_lock:
            rec = self._sessions.get(session_id)
            if not rec or len(rec.messages) <= self.window:
                return
            old = rec.messages[: len(rec.messages) - self.window]
            rec.messages = rec.messages[-self.window:]
            rec.summary = await self._make_summary(rec.summary, old)
            rec.summarized_count += len(old)

    async def _make_summary(self, prev: str, messages: list[dict]) -> str:
        text = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in messages)
        llm = get_llm_client()
        if llm.mode == "llm":
            try:
                msgs = [
                    {"role": "system", "content": SUMMARY_SYSTEM},
                    {"role": "user", "content": f"已有摘要：{prev or '无'}\n\n新对话：\n{text}"},
                ]
                out = await llm.chat(msgs, temperature=0.2, max_tokens=300)
                if out:
                    return out[:500]
            except Exception:
                pass
        # 抽取式摘要：保留每轮用户消息要点 + 最近确认
        asks = [m["content"][:80] for m in messages if m["role"] == "user"][-4:]
        return (prev + " | " if prev else "") + "；".join(asks)[:400]

    def get_recent(self, session_id: str, n: int | None = None) -> list[dict]:
        rec = self._sessions.get(session_id)
        if not rec:
            return []
        n = n or self.window
        return rec.messages[-n:]

    def get_summary(self, session_id: str) -> str:
        rec = self._sessions.get(session_id)
        return rec.summary if rec else ""

    def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


_session_memory: SessionMemory | None = None


def get_session_memory() -> SessionMemory:
    global _session_memory
    if _session_memory is None:
        _session_memory = SessionMemory()
    return _session_memory
