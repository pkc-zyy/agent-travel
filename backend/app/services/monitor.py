"""运行监控（可观测性）：全链路记录 接口调用 / MCP 工具调用 / LLM 调用 / Agent 事件 / 业务流程。

- 内存环形缓冲（默认 2000 条），随手可查，无需外部分量
- 支持订阅（异步队列）→ `/api/monitor/stream` SSE 实时推送
- record() 为同步非阻塞函数，可在任意 async 上下文直接调用

用法：
    from app.services.monitor import get_monitor
    get_monitor().record("tool", "search_hotels", {"city": "丽江"}, duration_ms=35)
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Any

MAX_BUFFER = 2000
MAX_DETAIL_CHARS = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(value: Any, limit: int = 200) -> Any:
    """截断超长字符串，保证事件体积可控。"""
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"…(共{len(value)}字符)"
    return value


class Monitor:
    def __init__(self, buffer_size: int = MAX_BUFFER):
        self._buf: deque[dict] = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
        self._subs: set[asyncio.Queue] = set()
        self._next_id = 1
        self._counters: Counter = Counter()          # (type, status)
        self._name_counters: Counter = Counter()     # type → name 调用次数
        self._durations: dict[str, deque[float]] = {}

    # ---------- 记录 ----------
    def record(
        self,
        type: str,
        name: str,
        detail: dict[str, Any] | None = None,
        duration_ms: float | None = None,
        status: str = "ok",
        session_id: str = "",
    ) -> dict:
        """记录一条监控事件（同步、非阻塞）。type: api|tool|llm|agent|flow|error"""
        event = {
            "id": 0,
            "ts": _now_iso(),
            "type": type,
            "name": name,
            "detail": {k: _clip(v) for k, v in (detail or {}).items()},
            "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
            "status": status,
            "session_id": session_id,
        }
        with self._lock:
            event["id"] = self._next_id
            self._next_id += 1
            self._buf.append(event)
            self._counters[(type, status)] += 1
            self._name_counters[f"{type}:{name}"] += 1
            if duration_ms is not None:
                dq = self._durations.setdefault(type, deque(maxlen=200))
                dq.append(duration_ms)

        # 推送给 SSE 订阅者（失败忽略，不影响主流程）
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    def timed(self, type: str, name: str, session_id: str = "") -> "TimedRecord":
        """上下文管理器：自动计时记录。"""
        return TimedRecord(self, type, name, session_id)

    # ---------- 查询 ----------
    def recent(self, limit: int = 200, type: str | None = None,
               status: str | None = None, q: str | None = None) -> list[dict]:
        """按时间倒序返回最近事件（最新在前）。"""
        with self._lock:
            items = list(self._buf)
        items.reverse()
        out = []
        for ev in items:
            if type and ev["type"] != type:
                continue
            if status and ev["status"] != status:
                continue
            if q and q.lower() not in ev["name"].lower():
                continue
            out.append(ev)
            if len(out) >= limit:
                break
        return out

    def summary(self) -> dict:
        with self._lock:
            by_type = {}
            for (type, status), n in self._counters.items():
                by_type.setdefault(type, {"total": 0, "errors": 0})
                by_type[type]["total"] += n
                if status == "error":
                    by_type[type]["errors"] += n
            top = self._name_counters.most_common(12)
            avg = {
                type: round(sum(dq) / len(dq), 1)
                for type, dq in self._durations.items()
                if dq
            }
            return {
                "total": sum(n for (_, _), n in self._counters.items()),
                "by_type": by_type,
                "by_name_top": [{"name": name, "count": n} for name, n in top],
                "avg_ms": avg,
                "buffer_size": len(self._buf),
                "ts": _now_iso(),
            }

    # ---------- 订阅（SSE 实时推送） ----------
    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)


class TimedRecord:
    """`with monitor.timed("tool", name): ...` 自动计时的上下文管理器。"""

    def __init__(self, monitor: Monitor, type: str, name: str, session_id: str = ""):
        self._monitor = monitor
        self._type = type
        self._name = name
        self._session_id = session_id
        self._start = 0.0
        self.detail: dict[str, Any] = {}

    def __enter__(self) -> "TimedRecord":
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        ms = (time.monotonic() - self._start) * 1000
        if exc is not None:
            self.detail["error"] = _clip(str(exc), 300)
            self._monitor.record(self._type, self._name, self.detail, ms, status="error",
                                 session_id=self._session_id)
        else:
            self._monitor.record(self._type, self._name, self.detail, ms, session_id=self._session_id)
        return False  # 不吞异常

    async def __aenter__(self) -> "TimedRecord":
        self._start = time.monotonic()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return self.__exit__(exc_type, exc, tb)


_monitor: Monitor | None = None


def get_monitor() -> Monitor:
    global _monitor
    if _monitor is None:
        _monitor = Monitor()
    return _monitor
