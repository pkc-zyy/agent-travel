"""天气顾问 Agent：通过 MCP 工具查询多城市天气（并发执行）。"""
from __future__ import annotations

import asyncio

from app.agents.base import AgentContext, BaseAgent


class WeatherAgent(BaseAgent):
    name = "天气顾问"
    emoji = "☀️"
    role = "查询目的地天气，给出出行建议"

    async def run(self, cities: list[str], dates: list[str | None] | None = None) -> list[dict]:
        await self.emit("running", f"正在查询 {len(cities)} 个城市的天气…")

        async def one(city: str, date_: str | None) -> dict | None:
            try:
                return await self.mcp.call_tool("get_weather", {"city": city, "date": date_})
            except Exception as e:
                await self.emit("error", f"{city} 天气查询失败：{e}")
                return None

        dates = dates or [None] * len(cities)
        results = await asyncio.gather(*(one(c, d) for c, d in zip(cities, dates)))
        weather = [r for r in results if r]
        await self.emit("done", f"天气数据获取完成（{len(weather)}/{len(cities)} 城市）")
        return weather
