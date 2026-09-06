"""实时搜索员 Agent：通过 MCP 工具进行网页搜索，补充互联网最新信息。

用途：规划行程时并行搜索目的地的最新攻略、门票、开放时间、实时活动等，
弥补本地知识库无法覆盖的实时信息。
"""
from __future__ import annotations

import asyncio

from app.agents.base import AgentContext, BaseAgent


class WebSearcherAgent(BaseAgent):
    name = "实时搜索员"
    emoji = "🌐"
    role = "搜索互联网最新信息（门票/开放时间/实时活动）"

    async def run(self, cities: list[str], queries: list[str] | None = None, top_k: int = 3) -> list[dict]:
        """对每个城市执行网页搜索（并发），返回 [{query, city, results:[...]}]。"""
        tasks: list[tuple[str, str]] = []
        if queries:
            tasks = [(q, "") for q in queries]
        else:
            for city in cities:
                tasks.append((f"{city} 旅游 最新攻略 门票 开放时间", city))

        await self.emit("running", f"正在搜索 {len(tasks)} 个主题的互联网实时信息…")

        async def one(query: str, city: str) -> dict | None:
            try:
                results = await self.mcp.call_tool("web_search", {"query": query, "top_k": top_k})
                return {"query": query, "city": city, "results": results if isinstance(results, list) else []}
            except Exception as e:
                await self.emit("error", f"搜索「{query}」失败：{e}")
                return {"query": query, "city": city, "results": []}

        out = await asyncio.gather(*(one(q, c) for q, c in tasks))
        fetched = [r for r in out if r and r.get("results")]
        await self.emit("done", f"网页搜索完成（{len(fetched)}/{len(tasks)} 个主题有结果）")
        return fetched

    def render(self, results: list[dict]) -> str:
        """渲染为 Markdown。"""
        if not results:
            return ""
        lines = ["### 🌐 实时信息（网页搜索）", ""]
        for group in results:
            lines.append(f"**{group['query']}**")
            for r in group.get("results", [])[:3]:
                lines.append(f"- [{r.get('title', '')}]({r.get('url', '')})（{r.get('source', '')}）")
                if r.get("snippet"):
                    lines.append(f"  {r.get('snippet', '')[:120]}")
        return "\n".join(lines)
