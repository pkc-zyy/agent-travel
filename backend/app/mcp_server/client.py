"""MCP 客户端：通过 MCP 协议（进程内 memory transport）调用 TravelAgent MCP Server 工具。

Agent 不直接调用服务层，而是统一经 MCP 协议调用工具 —— 体现「Agent + MCP」的标准架构：
Agent(host) ──MCP JSON-RPC──> MCP Server(tools)

生命周期：应用启动时懒连接，关闭时须调用 aclose() 释放（否则 asyncio 关闭时残留任务）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.mcp_server.travel_mcp import mcp as travel_mcp_server
from app.services.monitor import get_monitor

logger = logging.getLogger(__name__)


class TravelMCPClient:
    def __init__(self):
        self._cm = None          # async context manager（holding task group）
        self._session = None     # ClientSession
        self._started = False
        # MCP 协议层非线程/任务安全（memory transport 的 anyio task group 不能跨任务并发），
        # 用锁串行化协议操作，保证并发 Agent 调用安全
        self._lock = asyncio.Lock()

    async def _ensure_session(self):
        if self._started:
            return
        async with self._lock:
            if self._started:
                return
            # 进程内连接：真实 MCP 协议会话（initialize → tools/list → tools/call）
            from mcp.shared.memory import create_connected_server_and_client_session

            self._cm = create_connected_server_and_client_session(travel_mcp_server)
            self._session = await self._cm.__aenter__()
            self._started = True
            logger.info("MCP 会话已建立（in-memory transport）")

    async def list_tools(self) -> list[str]:
        await self._ensure_session()
        async with self._lock:
            tools = await self._session.list_tools()
            return [t.name for t in tools.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """调用 MCP 工具，返回解析后的结构化数据。全过程记录到运行监控。"""
        await self._ensure_session()
        monitor = get_monitor()
        started = time.monotonic()
        async with self._lock:
            try:
                result = await self._session.call_tool(name, arguments=arguments or {})
            except Exception as e:
                ms = (time.monotonic() - started) * 1000
                monitor.record("tool", name, {
                    "args": arguments or {},
                    "error": str(e)[:300],
                }, ms, status="error")
                raise
            ms = (time.monotonic() - started) * 1000

            if result.isError:
                text = "; ".join(c.text for c in result.content if hasattr(c, "text"))
                monitor.record("tool", name, {
                    "args": arguments or {},
                    "error": text[:300],
                }, ms, status="error")
                raise RuntimeError(f"MCP 工具 {name} 调用失败: {text or result}")

            # 解析输出：优先 structuredContent —— FastMCP 把 list 包装为 {"result": [...]}，
            # 可准确保留「列表 vs 单对象」类型（dict/str 返回无 structuredContent）
            sc = getattr(result, "structuredContent", None)
            if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
                output = sc["result"]
            elif isinstance(sc, dict):
                output = sc
            else:
                # 回退：逐条解析 TextContent（FastMCP 将 list[dict] 序列化为多条 JSON 文本）
                parsed: list[Any] = []
                for item in result.content:
                    if hasattr(item, "structured") and item.structured is not None:
                        parsed.append(item.structured)
                    elif hasattr(item, "text"):
                        try:
                            parsed.append(json.loads(item.text))
                        except json.JSONDecodeError:
                            parsed.append(item.text)
                if not parsed:
                    output = None
                elif len(parsed) == 1:
                    output = parsed[0]
                else:
                    output = parsed

            # 记录输出摘要（列表取条数，dict 取键，字符串截断）
            if isinstance(output, list):
                summary_out = f"返回 {len(output)} 条结果"
                preview = output[:2]
            elif isinstance(output, dict):
                summary_out = f"返回字段 {sorted(output.keys())[:8]}"
                preview = output
            else:
                summary_out = str(output)[:120] if output is not None else "返回空"
                preview = output
            monitor.record("tool", name, {
                "args": arguments or {},
                "output": summary_out,
                "preview": preview,
            }, ms)
            return output

    async def aclose(self):
        if self._cm is not None:
            async with self._lock:
                try:
                    await self._cm.__aexit__(None, None, None)
                except Exception as e:  # noqa: BLE001
                    logger.warning("MCP 会话关闭异常: %s", e)
        self._cm = None
        self._session = None
        self._started = False


_mcp_client: TravelMCPClient | None = None


def get_mcp_client() -> TravelMCPClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = TravelMCPClient()
    return _mcp_client
