"""TravelAgent 后端入口：FastAPI 应用装配。

启动：uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.sse import SseServerTransport
from starlette.routing import Route
from starlette.applications import Starlette

from app.api import (
    chat,
    feedback,
    knowledge,
    memory,
    monitor,
    orders,
    plans,
    settings as settings_api,
    stats,
)
from app.config import get_settings
from app.db.database import init_db
from app.mcp_server.travel_mcp import mcp as travel_mcp
from app.services.monitor import get_monitor
from app.services.runtime_config import is_llm_ready

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("travelagent")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) 初始化数据库
    await init_db()
    logger.info("数据库初始化完成")

    # 2) 后台构建 RAG 索引（向量 + BM25）
    from app.rag.knowledge import get_knowledge_base

    kb = get_knowledge_base()
    build_task = asyncio.create_task(kb.build())
    await build_task
    logger.info("RAG 知识库就绪: %s", kb.stats())

    yield
    # 关闭时清理
    try:
        from app.mcp_server.client import get_mcp_client

        await get_mcp_client().aclose()
    except Exception:
        pass


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

# CORS：允许前端开发服务器与部署地址
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 运行监控：HTTP 接口调用全量记录 ====================
_monitor = get_monitor()
_SKIP_MARKERS = ("/monitor", "/mcp", "/docs", "/openapi.json")  # 监控/文档自身不记录（避免自激污染数据）


@app.middleware("http")
async def monitor_http_requests(request: Request, call_next):
    start = time.monotonic()
    path = request.url.path
    try:
        response = await call_next(request)
    except Exception as e:
        ms = (time.monotonic() - start) * 1000
        if not any(m in path for m in _SKIP_MARKERS):
            _monitor.record("api", f"{request.method} {path}",
                            {"error": str(e)[:200]}, ms, status="error")
        raise
    ms = (time.monotonic() - start) * 1000
    if not any(m in path for m in _SKIP_MARKERS):
        _monitor.record(
            "api",
            f"{request.method} {path}",
            {"status_code": response.status_code,
             "client": request.client.host if request.client else ""},
            ms,
            status="error" if response.status_code >= 500 else "ok",
        )
    return response

# ==================== MCP Server（SSE 传输） ====================
_mcp_transport = SseServerTransport("/messages/")


async def _handle_mcp_sse(request):
    # mcp>=1.29 的 SseServerTransport 只有 connect_sse（旧的 handle_sse 已移除）
    async with _mcp_transport.connect_sse(request.scope, request.receive, request._send) as (
        reader,
        writer,
    ):
        await travel_mcp._mcp_server.run(
            reader,
            writer,
            travel_mcp._mcp_server.create_initialization_options(),
        )


async def _handle_mcp_post(request):
    # mcp>=1.29 的 handle_post_message 是原生 ASGI 签名 (scope, receive, send)
    await _mcp_transport.handle_post_message(request.scope, request.receive, request._send)


_mcp_app = Starlette(
    routes=[
        # 挂载在 /mcp 前缀下，内部路径 "/" 即外部 GET /mcp（SSE 流）
        Route("/", _handle_mcp_sse),
        Route("/messages/", _handle_mcp_post, methods=["POST"]),
    ]
)
app.mount("/mcp", _mcp_app, name="mcp")


# ==================== 业务 API ====================
for r in (
    chat.router,
    plans.router,
    feedback.router,
    memory.router,
    knowledge.router,
    settings_api.router,
    orders.router,
    stats.router,
    monitor.router,
):
    app.include_router(r, prefix=settings.api_prefix)


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "api": f"{settings.api_prefix}",
        "mcp_endpoint": "/mcp",
        "llm_mode": "llm" if is_llm_ready() else "offline",
    }
