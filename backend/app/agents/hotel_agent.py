"""酒店专家 Agent：通过 MCP 工具按城市/预算/偏好推荐酒店（并发执行）。"""
from __future__ import annotations

import asyncio

from app.agents.base import AgentContext, BaseAgent, TripSpec


class HotelAgent(BaseAgent):
    name = "酒店专家"
    emoji = "🏨"
    role = "按预算与偏好筛选住宿推荐"

    async def run(self, cities: list[str], spec: TripSpec) -> list[dict]:
        keywords = ",".join(spec.preferences[:3])
        await self.emit("running", f"正在为 {len(cities)} 个城市筛选酒店（预算：{spec.budget_level}型）…")

        async def one(city: str) -> list[dict]:
            try:
                result = await self.mcp.call_tool(
                    "search_hotels",
                    {
                        "city": city,
                        "budget": spec.budget_level,
                        "keywords": keywords,
                        "top_k": 3,
                    },
                )
                return result if isinstance(result, list) else []
            except Exception as e:
                await self.emit("error", f"{city} 酒店查询失败：{e}")
                return []

        results = await asyncio.gather(*(one(c) for c in cities))
        hotels = [h for lst in results for h in lst]
        await self.emit("done", f"酒店推荐完成，共 {len(hotels)} 家")
        return hotels

    def pick_for_city(self, hotels: list[dict], city: str) -> dict | None:
        for h in hotels:
            if h.get("city") == city:
                return h
        return None
