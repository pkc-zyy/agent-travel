"""监控 API：实时查看 接口调用 / 工具调用 / LLM / Agent 全链路事件。

- GET /api/monitor/events   最近事件（可按 type/status/名称过滤）
- GET /api/monitor/summary  汇总统计（按类型计数、Top 调用、平均耗时）
- GET /api/monitor/stream   SSE 实时推送（随时监测，无需轮询）
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.services.monitor import get_monitor

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/events")
async def list_events(
    limit: int = Query(200, ge=1, le=2000),
    type: str | None = None,
    status: str | None = None,
    q: str | None = None,
):
    """最近监控事件（最新在前）。type: api|tool|llm|agent|flow|error"""
    return {"events": get_monitor().recent(limit=limit, type=type, status=status, q=q)}


@router.get("/summary")
async def monitor_summary():
    return get_monitor().summary()


@router.get("/stream")
async def monitor_stream():
    """SSE 实时事件流：每条监控事件即时推送，用于前端「监控中心」实时刷新。"""
    monitor = get_monitor()

    async def event_stream():
        queue = await monitor.subscribe()
        try:
            yield sse({"type": "hello", "message": "监控已连接"})
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=20)
                    yield sse({"type": "event", "event": ev})
                except asyncio.TimeoutError:
                    yield sse({"type": "ping"})
        finally:
            monitor.unsubscribe(queue)

    def sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
