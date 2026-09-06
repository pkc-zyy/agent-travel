"""景点研究员 Agent：通过 MCP 工具按城市/兴趣推荐景点（并发执行）。"""
from __future__ import annotations

import asyncio

from app.agents.base import AgentContext, BaseAgent, TripSpec


class AttractionAgent(BaseAgent):
    name = "景点研究员"
    emoji = "🏔️"
    role = "挖掘目的地值得一去的景点"

    async def run(self, cities: list[str], spec: TripSpec) -> list[dict]:
        interests = ",".join(spec.preferences[:4])
        await self.emit("running", f"正在研究 {len(cities)} 个城市的景点（兴趣：{interests or '综合'}）…")

        async def one(city: str) -> list[dict]:
            try:
                result = await self.mcp.call_tool(
                    "search_attractions",
                    {"city": city, "interests": interests, "top_k": 6},
                )
                return result if isinstance(result, list) else []
            except Exception as e:
                await self.emit("error", f"{city} 景点查询失败：{e}")
                return []

        results = await asyncio.gather(*(one(c) for c in cities))
        attractions = [a for lst in results for a in lst]
        await self.emit("done", f"景点研究完成，共 {len(attractions)} 个景点")
        return attractions

    def pick_for_city(self, attractions: list[dict], city: str) -> list[dict]:
        return [a for a in attractions if a.get("city") == city]
