"""方案审查官 Agent（质量门禁）+ 预算会计师 Agent。"""
from __future__ import annotations

from app.agents.base import AgentContext, BaseAgent, TripSpec

_BUDGET_DAILY = {"经济": 250, "舒适": 600, "豪华": 1500}


class ReviewerAgent(BaseAgent):
    name = "方案审查官"
    emoji = "🕵️"
    role = "审查方案的完整性、节奏与预算合理性"

    async def review(self, plan: dict, spec: TripSpec) -> tuple[bool, list[str], int]:
        """返回 (是否通过, 问题列表, 评分)。"""
        issues: list[str] = []
        score = 90
        schedule = plan.get("schedule", [])

        if not schedule:
            return False, ["行程为空"], 0

        # 1) 覆盖度：每个城市都有景点与酒店
        city_attrs: dict[str, int] = {}
        city_hotels: dict[str, int] = {}
        for day in schedule:
            city = day.get("city", "")
            city_attrs[city] = city_attrs.get(city, 0) + len(day.get("attractions", []))
            if day.get("hotel"):
                city_hotels[city] = city_hotels.get(city, 0) + 1
        for city in set(spec.cities):
            if city_attrs.get(city, 0) == 0:
                issues.append(f"{city} 缺少景点安排")
                score -= 8
            if city_hotels.get(city, 0) == 0:
                issues.append(f"{city} 缺少住宿推荐")
                score -= 8

        # 2) 节奏：每天活动 2~4 项为宜
        for day in schedule:
            n = len(day.get("activities", []))
            if n < 2:
                issues.append(f"Day{day.get('day')} 活动过少")
                score -= 5
            elif n > 5:
                issues.append(f"Day{day.get('day')} 安排过满，建议精简")
                score -= 3

        # 3) 景点重复：同一景点全程只应出现一次
        seen: set[str] = set()
        for day in schedule:
            for a in day.get("attractions", []):
                name = a.get("name", "")
                if name and name in seen:
                    issues.append(f"景点「{name}」在行程中重复出现")
                    score -= 10
                seen.add(name)

        # 4) 距离合理性：当日景点与酒店/前站的估算车程不宜过远
        for day in schedule:
            for a in day.get("attractions", []):
                km = a.get("distance_km")
                if isinstance(km, (int, float)) and km > 45:
                    issues.append(
                        f"Day{day.get('day')} 「{a.get('name')}」距前站约 {km} km，建议调整顺序或拆分到独立一天"
                    )
                    score -= 6

        # 3) 预算合理性
        if plan.get("budget", {}).get("total_per_person"):
            daily = _BUDGET_DAILY.get(spec.budget_level, 600)
            estimate = plan["budget"]["total_per_person"] / max(1, plan.get("days", 1))
            if estimate > daily * 1.8:
                issues.append("预算可能偏高，可考虑更经济的交通/住宿")
                score -= 5

        passed = len(issues) == 0 or score >= 78
        await self.emit("done", f"审查完成：评分 {max(0, score)}，{'通过 ✅' if passed else '需优化 ⚠️'}")
        return passed, issues, max(0, score)


class BudgetAgent(BaseAgent):
    name = "预算会计师"
    emoji = "💰"
    role = "核算行程成本，给出人均预算明细"

    async def calculate(self, plan: dict, spec: TripSpec) -> dict:
        await self.emit("running", "正在核算行程预算…")
        days = plan.get("days", 1)
        n_cities = len(plan.get("cities", []))

        # 城际交通：高铁/飞机估算，每段约 400 元
        transport = max(0, n_cities - 1) * 400 + 120

        # 住宿：取推荐酒店均价（按双人分摊）
        hotels = plan.get("hotels", [])
        if hotels:
            hotel_price = sum(h.get("price", 0) for h in hotels) / len(hotels) / 2 * days
        else:
            daily = _BUDGET_DAILY.get(spec.budget_level, 600)
            hotel_price = daily * 0.45 * days

        # 餐饮：按预算档位
        food = _BUDGET_DAILY.get(spec.budget_level, 600) * 0.35 * days

        # 门票：推荐景点门票合计
        tickets = sum(a.get("price", 0) for a in plan.get("attractions", []))

        total = int(transport + hotel_price + food + tickets)
        detail = {
            "transport": int(transport),
            "hotel": int(hotel_price),
            "food": int(food),
            "tickets": int(tickets),
            "total_per_person": total,
            "currency": "CNY",
        }
        await self.emit("done", f"预算核算完成：人均约 {total} 元")
        return detail
