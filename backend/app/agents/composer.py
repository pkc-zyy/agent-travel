"""Markdown 渲染器：把结构化数据（天气/酒店/景点/行程）渲染为整洁的中文 Markdown。"""
from __future__ import annotations

from typing import Any


def render_weather(weather_list: list[dict]) -> str:
    if not weather_list:
        return ""
    lines = ["### ☀️ 目的地天气", ""]
    for w in weather_list:
        cond = w.get("condition", "")
        src = "实时" if w.get("source") == "open-meteo" else "预估"
        lines.append(
            f"- **{w.get('city', '')}**：{cond}，{w.get('t_min')}~{w.get('t_max')}℃，"
            f"降水概率 {w.get('precip_prob', 0)}%（{src}数据）"
        )
    return "\n".join(lines)


def render_hotels(hotels: list[dict]) -> str:
    if not hotels:
        return ""
    lines = ["### 🏨 酒店推荐", ""]
    for h in hotels:
        tags = " · ".join(h.get("tags", []))
        loc = h.get("address") or ""
        lines.append(
            f"- **{h.get('name', '')}**（{h.get('city', '')}）约 {h.get('price', 0)} 元/晚，"
            f"评分 {h.get('rating', 0)}｜{h.get('desc', '')}"
            + (f"｜地址：{loc}" if loc else "")
            + (f"｜标签：{tags}" if tags else "")
        )
    return "\n".join(lines)


def render_attractions(attrs: list[dict]) -> str:
    if not attrs:
        return ""
    lines = ["### 🏔️ 景点推荐", ""]
    for a in attrs:
        mark = "✅" if a.get("scheduled") else "○ 备选"
        km = a.get("distance_km")
        dist = f"，距前站约 {km} km" if isinstance(km, (int, float)) and km >= 0.3 else ""
        lines.append(
            f"- {mark} **{a.get('name', '')}**（{a.get('city', '')}）门票约 {a.get('price', 0)} 元，"
            f"建议 {a.get('duration', '')}{dist}｜{a.get('desc', '')}"
        )
    return "\n".join(lines)


def render_plan(plan: dict) -> str:
    """完整行程方案 Markdown。"""
    title = plan.get("title", "旅行方案")
    lines = [f"# ✈️ {title}", ""]

    summary = plan.get("summary", "")
    if summary:
        lines += [summary, ""]

    # 概览
    cities = " → ".join(plan.get("cities", []))
    budget = plan.get("budget_range", "")
    lines.append("## 📋 行程概览")
    lines.append(f"- 城市路线：**{cities}**")
    lines.append(f"- 行程天数：**{plan.get('days', 0)} 天**")
    if budget:
        lines.append(f"- 预算范围：**{budget}**")
    travelers = plan.get("travelers", "")
    if travelers:
        lines.append(f"- 出行人员：{travelers}")
    lines.append("")

    # 每日行程
    lines.append("## 🗓️ 每日行程")
    lines.append("")
    for day in plan.get("schedule", []):
        lines.append(f"### Day {day.get('day')} · {day.get('city', '')}")
        lines.append(f"**主题**：{day.get('title', '')}")
        w = day.get("weather")
        if w:
            lines.append(
                f"**天气**：{w.get('condition', '')}，{w.get('t_min')}~{w.get('t_max')}℃"
            )
        lines.append("")
        lines.append("**活动安排**：")
        for act in day.get("activities", []):
            lines.append(f"- {act}")
        lines.append("")
        route = day.get("route_summary")
        if route:
            lines.append(f"**🧭 当日动线**：{route}")
            lines.append("")
        hotel = day.get("hotel")
        if hotel:
            lines.append(f"**住宿**：{hotel.get('name', '')}（约 {hotel.get('price', 0)} 元/晚）")
        meal = day.get("meals", [])
        if meal:
            lines.append(f"**美食**：{'、'.join(meal)}")
        transport = day.get("transport", "")
        if transport:
            lines.append(f"**交通**：{transport}")
        lines.append("")

    # 酒店汇总（含选址策略说明）
    strategy = plan.get("hotel_strategy") or {}
    if hotels_list := plan.get("hotels"):
        if strategy:
            stats = "，".join(
                f"{city} 平均距景点约 {s.get('avg_km')} km"
                for city, s in strategy.items()
                if s.get("avg_km") is not None
            )
            if stats:
                lines += [f"> 🧭 酒店按「贴近景点群」自动选址：{stats}", ""]
        lines += [render_hotels(hotels_list), ""]

    # 景点汇总
    if plan.get("attractions"):
        lines += [render_attractions(plan["attractions"]), ""]

    # 实时信息（网页搜索）
    web_results = plan.get("web_results", [])
    if web_results:
        lines.append("## 🌐 实时信息（网页搜索）")
        lines.append("")
        for group in web_results:
            lines.append(f"**{group.get('query', '')}**")
            for r in (group.get("results") or [])[:3]:
                title = r.get("title", "")
                url = r.get("url", "")
                lines.append(f"- [{title}]({url})（{r.get('source', '')}）")
                if r.get("snippet"):
                    lines.append(f"  {r.get('snippet', '')[:120]}")
        lines.append("")

    # 预算
    budget_detail = plan.get("budget", {})
    if budget_detail:
        lines.append("## 💰 预算明细（人均估算）")
        lines.append("")
        lines.append("| 项目 | 金额 |")
        lines.append("| --- | --- |")
        for key, label in [
            ("transport", "城际交通"),
            ("hotel", "住宿"),
            ("food", "餐饮"),
            ("tickets", "门票"),
        ]:
            if budget_detail.get(key):
                lines.append(f"| {label} | 约 {budget_detail[key]} 元 |")
        lines.append(f"| **合计** | **约 {budget_detail.get('total_per_person', 0)} 元/人** |")
        lines.append("")

    # 贴士
    tips = plan.get("tips", [])
    if tips:
        lines.append("## 💡 温馨提示")
        lines.append("")
        for t in tips:
            lines.append(f"- {t}")
        lines.append("")

    # 参与智能体
    agents = plan.get("agents", [])
    if agents:
        lines.append("---")
        lines.append("")
        lines.append("## 🤖 本次协作智能体")
        lines.append("")
        for a in agents:
            lines.append(f"- {a.get('emoji', '')} **{a.get('name', '')}**（{a.get('role', '')}）")
        lines.append("")

    return "\n".join(lines)
