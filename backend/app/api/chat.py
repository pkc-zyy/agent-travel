"""聊天 API：支持 SSE 流式（智能体事件 + 最终结果）与普通 JSON 两种模式。"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agents.orchestrator import get_orchestrator
from app.models import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


async def _noop(ev: dict) -> None:
    pass


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """非流式：一次返回完整回复（供测试/简单客户端使用）。"""
    try:
        result = await get_orchestrator().handle(
            req.message, req.session_id, req.user_id, emit=_noop
        )
    except Exception as e:
        logger.exception("chat failed")
        raise HTTPException(status_code=500, detail=f"智能体处理失败: {e}")
    return ChatResponse(
        session_id=req.session_id,
        user_id=req.user_id,
        reply=result["reply"],
        intent=result["intent"],
        data=result["data"],
    )


@router.post("/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """SSE 流式：推送 智能体协作事件 → 结构化数据 → 最终回复。"""
    if not req.stream:
        return await chat(req)

    async def event_stream():
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def emit(ev: dict) -> None:
            await queue.put(ev)

        task = asyncio.create_task(
            get_orchestrator().handle(req.message, req.session_id, req.user_id, emit)
        )

        def sse(ev: dict) -> str:
            return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

        try:
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    if task.done():
                        break
                    yield sse({"type": "ping"})
                    continue
                yield sse(ev)
                if ev.get("type") == "done":
                    break
            # 等待智能体完成并推送完整结果（含结构化数据）
            result = await task
            yield sse(
                {
                    "type": "result",
                    "intent": result["intent"],
                    "reply": result["reply"],
                    "data": result["data"],
                }
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("SSE stream error")
            yield sse({"type": "error", "message": str(e)})
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
