"""主管协调器（Orchestrator / Supervisor）：意图识别 → 任务分发 → 多 Agent 并发协作 → 整合输出。

协作模式：
  主管（Supervisor）──┐
      ├── 行程规划师（框架/整合）
      ├── 天气顾问 ──┐
      ├── 酒店专家 ──┼── asyncio.gather 并发执行（互相独立，可并行）
      └── 景点研究员 ─┘
      └── 预算会计师 / 方案审查官（串行门禁）

所有专家通过 MCP 协议调用工具（天气/酒店/景点/RAG），体现 Agent + MCP 架构。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Awaitable, Callable

from app.agents.attraction_agent import AttractionAgent
from app.agents.base import AgentContext, TripSpec
from app.agents.composer import render_attractions, render_hotels, render_weather
from app.agents.feedback_agent import FeedbackAgent
from app.agents.hotel_agent import HotelAgent
from app.agents.planner import PlannerAgent
from app.agents.reviewer import BudgetAgent, ReviewerAgent
from app.agents.weather_agent import WeatherAgent
from app.agents.web_searcher import WebSearcherAgent
from app.config import get_settings
from app.mcp_server.client import get_mcp_client
from app.memory.context import get_context_manager
from app.memory.longterm import get_long_term_memory
from app.memory.session import get_session_memory
from app.rag.knowledge import get_knowledge_base
from app.services.catalog import get_city_info, known_cities
from app.services.llm import get_llm_client

logger = logging.getLogger(__name__)

EmitFn = Callable[[dict], Awaitable[None]]

_INTENT_RULES = [
    ("feedback", re.compile(r"反馈|意见|建议|评价|吐槽|投诉|改进|打分")),
    ("weather", re.compile(r"天气|气温|温度|下雨|下雪|冷不冷|热不热|降水")),
    ("hotel", re.compile(r"酒店|住宿|民宿|旅馆|住哪|订房|入住")),
    ("attraction", re.compile(r"景点|好玩|必去|打卡|游览|值得去|去哪儿|哪里好玩|景区")),
    ("plan", re.compile(r"规划|行程|路线|攻略|安排|日游|几天|旅游|旅行|度假|玩|怎么走")),
]


def classify_intent(text: str) -> str:
    """基于规则的意图识别；有规划类关键词且命中城市时优先规划。"""
    has_city = any(c in text for c in known_cities())
    has_plan = _INTENT_RULES[4][1].search(text) is not None
    if has_plan and has_city:
        return "plan"
    for name, pattern in _INTENT_RULES[:4]:
        if pattern.search(text):
            return name
    if has_plan:
        return "plan"
    if re.search(r"你好|您好|hi|hello|help|帮助|能做什么|介绍一下", text, re.I):
        return "greeting"
    return "general"


class Orchestrator:
    def __init__(self):
        self.settings = get_settings()
        self.mcp = get_mcp_client()
        self.context_manager = get_context_manager()
        self._last_hotel_stats: dict[str, dict] = {}  # 每城酒店选址策略（由 _build_schedule 更新）

    # ==================== 主入口 ====================
    async def handle(self, request: str, session_id: str, user_id: str,
                     emit: EmitFn) -> dict[str, Any]:
        """处理单条用户消息，返回 {reply, intent, data}。全程记录运行监控。"""
        from app.services.monitor import get_monitor

        monitor = get_monitor()
        flow_started = time.monotonic()

        # 1) 组装上下文（长期记忆 + RAG + 会话历史）
        packet = await self.context_manager.build(user_id, session_id, request)

        # 2) 意图识别
        intent = classify_intent(request)
        await emit({"type": "agent", "agent": "orchestrator", "name": "主管协调器",
                    "emoji": "🧠", "role": "协调专家智能体协同工作",
                    "status": "running", "message": f"意图识别：{intent}"})

        ctx = AgentContext(
            user_id=user_id,
            session_id=session_id,
            request=request,
            packet=packet,
            mcp=self.mcp,
            settings=self.settings,
            extra={"emit": emit},
        )

        # 3) 路由分发
        if intent == "plan":
            result = await self._plan_flow(ctx, emit)
        elif intent == "weather":
            result = await self._weather_flow(ctx, emit)
        elif intent == "hotel":
            result = await self._hotel_flow(ctx, emit)
        elif intent == "attraction":
            result = await self._attraction_flow(ctx, emit)
        elif intent == "feedback":
            result = await self._feedback_flow(ctx, emit)
        elif intent == "greeting":
            result = await self._greeting_flow(ctx, emit)
        else:
            result = await self._general_flow(ctx, emit)

        # 4) 记忆沉淀 + 会话更新
        try:
            await get_long_term_memory().extract_and_store(user_id, request)
        except Exception as e:
            logger.warning("记忆抽取失败: %s", e)
        sm = get_session_memory()
        sm.add_message(session_id, "user", request)
        sm.add_message(session_id, "assistant", result.get("reply", ""))

        # 全流程监控：意图 / 总耗时 / 回复摘要
        monitor.record("flow", f"对话流程·{intent}", {
            "request": request[:120],
            "reply": (result.get("reply") or "")[:150],
            "reply_chars": len(result.get("reply") or ""),
            "has_plan": "plan" in (result.get("data") or {}),
            "has_order_offer": bool((result.get("data") or {}).get("order_offer")),
        }, (time.monotonic() - flow_started) * 1000, session_id=session_id)

        await emit({"type": "done"})
        return {"reply": result.get("reply", ""), "intent": intent, "data": result.get("data")}

    # ==================== 规划主流程 ====================
    async def _plan_flow(self, ctx: AgentContext, emit: EmitFn) -> dict:
        planner = PlannerAgent(ctx)
        weather_agent = WeatherAgent(ctx)
        hotel_agent = HotelAgent(ctx)
        attraction_agent = AttractionAgent(ctx)
        web_searcher = WebSearcherAgent(ctx)
        reviewer = ReviewerAgent(ctx)
        budget_agent = BudgetAgent(ctx)

        # 1) 解析需求
        spec = await planner.parse_request(ctx.request)
        if spec.needs_more_info:
            await emit({"type": "agent", "agent": "orchestrator", "name": "主管协调器",
                        "emoji": "🧠", "role": "协调专家智能体协同工作",
                        "status": "done", "message": "需要补充目的地信息"})
            return {"reply": f"📌 还需要一些信息：{spec.needs_more_info}\n\n也可以试试示例：「帮我规划云南昆明-大理-丽江 5 日游，人均 4000，喜欢自然风光」"}

        framework = planner.build_framework(spec)
        cities = list(dict.fromkeys(spec.cities))

        # 2) 并发分发：天气 / 酒店 / 景点 / 实时搜索 四路并行
        weather, hotels, attractions, web_results = await asyncio.gather(
            weather_agent.run(cities),
            hotel_agent.run(cities, spec),
            attraction_agent.run(cities, spec),
            web_searcher.run(cities),
        )

        # 3) 组装每日行程（地理就近路由 + 酒店贴近景点群）
        schedule = self._build_schedule(framework, spec, weather, hotels, attractions)
        scheduled_names = {a["name"] for d in schedule for a in d.get("attractions", [])}
        for a in attractions:
            a["scheduled"] = a.get("name") in scheduled_names
        if hotels:
            from app.services.geo import dedupe_by_name

            hotels = dedupe_by_name(hotels)  # 多城共享一个列表时按名称去重

        plan: dict[str, Any] = {
            "title": f"{' · '.join(cities)} {spec.days} 日游方案",
            "summary": self._make_summary(spec, cities),
            "cities": cities,
            "days": spec.days,
            "budget_range": spec.budget or "待定",
            "travelers": spec.travelers,
            "start_date": spec.start_date,
            "preferences": spec.preferences,
            "schedule": schedule,
            "hotels": hotels,
            "attractions": attractions,
            "weather": weather,
            "web_results": web_results,
            "budget": {},
            "tips": [],
            "agents": [],
            "hotel_strategy": self._last_hotel_stats,
        }

        # 4) 预算核算 + 审查（质量门禁，可迭代优化一轮）
        plan["budget"] = await budget_agent.calculate(plan, spec)
        passed, issues, score = await reviewer.review(plan, spec)
        if not passed:
            await emit({"type": "agent", "agent": "orchestrator", "name": "主管协调器",
                        "emoji": "🧠", "role": "协调专家智能体协同工作",
                        "status": "running", "message": "审查未通过，安排一轮优化…"})
            # 简单优化：补齐缺失城市的基础数据
            plan = await self._refine_plan(plan, ctx, spec, emit)
            plan["budget"] = await budget_agent.calculate(plan, spec)
            passed, issues, score = await reviewer.review(plan, spec)
        plan["review"] = {"passed": passed, "score": score, "issues": issues}

        # 5) 贴士
        plan["tips"] = self._make_tips(spec, weather)

        # 6) 参与智能体记录
        plan["agents"] = [
            {"name": planner.name, "emoji": planner.emoji, "role": planner.role},
            {"name": weather_agent.name, "emoji": weather_agent.emoji, "role": weather_agent.role},
            {"name": hotel_agent.name, "emoji": hotel_agent.emoji, "role": hotel_agent.role},
            {"name": attraction_agent.name, "emoji": attraction_agent.emoji, "role": attraction_agent.role},
            {"name": web_searcher.name, "emoji": web_searcher.emoji, "role": web_searcher.role},
            {"name": budget_agent.name, "emoji": budget_agent.emoji, "role": budget_agent.role},
            {"name": reviewer.name, "emoji": reviewer.emoji, "role": reviewer.role},
        ]

        # 7) 整合 Markdown + 持久化
        markdown = await planner.integrate(plan)
        trip_id = await self._save_trip(ctx, plan)

        # 8) 生成「是否下单」询问（规划完成 → 主动询问客户，而不是让客户自己找入口）
        order_offer = None
        total = (plan.get("budget") or {}).get("total_per_person", 0)
        if trip_id is not None and total and total > 0:
            order_offer = {"trip_id": trip_id, "amount": total, "title": plan.get("title", "")}
            markdown += (
                "\n---\n\n"
                "## 🧾 方案确认\n\n"
                f"方案已生成并保存（行程 #{trip_id}）。**请问您需要为本次行程下单预订吗？**\n\n"
                f"- 预估金额：**约 {total} 元/人**\n"
                "- 点击下方「🧾 立即下单」即可生成支付订单（线下转账，人工确认到账后开通）\n"
                "- 也可以继续告诉我调整需求，例如「换成经济型酒店」「大理多待一天」\n"
            )
        plan["markdown"] = markdown

        await emit({"type": "agent", "agent": "orchestrator", "name": "主管协调器",
                    "emoji": "🧠", "role": "协调专家智能体协同工作",
                    "status": "done", "message": f"方案生成完成（审查评分 {score}），已保存到「我的行程」"})
        return {"reply": markdown, "data": {"plan": plan, "trip_id": trip_id, "order_offer": order_offer, "spec": {
            "cities": spec.cities, "days": spec.days, "budget": spec.budget,
            "preferences": spec.preferences, "travelers": spec.travelers,
        }}}

    # ---------- 每日行程组装 ----------
    def _build_schedule(self, framework: list[tuple[int, str]], spec: TripSpec,
                        weather: list[dict], hotels: list[dict],
                        attractions: list[dict]) -> list[dict]:
        """地理就近的每日行程组装：
        1. 同一景点全程只排一次（按城市切块分配到天，绝不重复）
        2. 每天景点按「酒店 → 最近邻」链式排序，当日动线紧凑
        3. 酒店按「贴近本城景点群」择优，同城多天住同一家
        """
        from app.services.geo import (
            city_route_summary,
            dedupe_by_name,
            loc_of,
            order_by_proximity,
            partition_days,
            pick_hotel_near_attractions,
        )

        planner = PlannerAgent.__new__(PlannerAgent)  # 仅用静态工具
        titles = planner.city_day_titles()
        city_weather: dict[str, dict] = {w.get("city"): w for w in weather}
        hotels_by_city: dict[str, list[dict]] = {}
        for h in hotels:
            hotels_by_city.setdefault(h.get("city"), []).append(h)
        city_attrs: dict[str, list[dict]] = {}
        for a in attractions:
            city_attrs.setdefault(a.get("city"), []).append(a)
        city_info = {c: get_city_info(c) for c in dict.fromkeys(spec.cities)}

        # 预处理：每城的天数 → 景点地理切块 + 酒店就近择优
        city_days: dict[str, int] = {}
        for _, city in framework:
            city_days[city] = city_days.get(city, 0) + 1
        blocks_by_city: dict[str, list[list[dict]]] = {}
        hotel_by_city: dict[str, dict | None] = {}
        hotel_stats: dict[str, dict] = {}
        for city, n_days in city_days.items():
            pool = dedupe_by_name(city_attrs.get(city, []))
            blocks_by_city[city] = partition_days(pool, n_days, per_day=2)
            hotel, stats = pick_hotel_near_attractions(hotels_by_city.get(city, []), pool)
            hotel_by_city[city] = hotel
            hotel_stats[city] = stats

        schedule: list[dict] = []
        prev_city: str | None = None
        block_idx: dict[str, int] = {}
        for day_no, city in framework:
            info = city_info.get(city, {})
            cuisine = info.get("cuisine", [])
            hotel = hotel_by_city.get(city)

            # 取该城下一个未使用的景点块（块内按酒店→最近邻排序，附每段车程）
            idx = block_idx.get(city, 0)
            block_idx[city] = idx + 1
            day_attrs = order_by_proximity(
                loc_of(hotel) if hotel else None, blocks_by_city.get(city, [[]])[idx] or []
            )

            activities: list[str] = []
            first_day_of_city = prev_city != city
            if day_no == 1 or first_day_of_city:
                activities.append(f"抵达{info.get('name', city)}，办理入住")
            for a in day_attrs:
                hop = a.get("distance_km")
                suffix = f"，距前站约 {hop} km" if isinstance(hop, (int, float)) and hop >= 0.3 else ""
                activities.append(f"游览 {a['name']}（{a.get('desc', '')[:28]}{suffix}）")
            if cuisine:
                activities.append(f"品尝当地美食：{'、'.join(cuisine[:2])}")
            if info.get("known_for"):
                activities.append(f"体验 {city} 特色：{'、'.join(info['known_for'][:2])}")
            if len(activities) < 2:
                # 景点少于天数时的休闲日（如 7 天游只有 8 个景点）
                activities.append(f"自由活动：漫步{info.get('name', city)}市区，探访本地生活街区")
                activities.append(f"慢享时光：按兴趣体验{city}的夜市/咖啡馆/温泉等休闲项目")

            schedule.append(
                {
                    "day": day_no,
                    "city": city,
                    "title": titles.get(city, f"{city}之旅"),
                    "weather": city_weather.get(city),
                    "attractions": day_attrs,
                    "hotel": hotel,
                    "meals": cuisine[:3],
                    "transport": self._transport_between(prev_city, city),
                    "route_summary": city_route_summary(day_attrs, hotel),
                    "activities": activities[:5],
                }
            )
            prev_city = city
        self._last_hotel_stats = hotel_stats
        return schedule

    @staticmethod
    def _transport_between(prev: str | None, city: str) -> str:
        if prev is None or prev == city:
            return ""
        return f"🚄 高铁 / ✈️ 航班 由 {prev} 前往 {city}"

    # ---------- 方案优化（审查未通过时） ----------
    async def _refine_plan(self, plan: dict, ctx: AgentContext, spec: TripSpec, emit: EmitFn) -> dict:
        attraction_agent = AttractionAgent(ctx)
        missing: list[str] = []
        for city in spec.cities:
            day = next((d for d in plan["schedule"] if d["city"] == city), None)
            if day and not day.get("attractions"):
                missing.append(city)
        if missing:
            extra = await attraction_agent.run(missing, spec)
            by_city: dict[str, list[dict]] = {}
            for a in extra:
                by_city.setdefault(a.get("city"), []).append(a)
            for day in plan["schedule"]:
                if day["city"] in by_city and not day.get("attractions"):
                    day["attractions"] = by_city[day["city"]][:2]
                    day["activities"] = [f"游览 {a['name']}" for a in day["attractions"]] + day["activities"]
        return plan

    # ==================== 单意图流程 ====================
    async def _cities_from_request(self, ctx: AgentContext) -> list[str]:
        cities = [c for c in known_cities() if c in ctx.request]
        if not cities and ctx.packet:
            for mem in ctx.packet.memories:
                for c in known_cities():
                    if c in mem.get("content", "") and c not in cities:
                        cities.append(c)
        return cities

    async def _weather_flow(self, ctx: AgentContext, emit: EmitFn) -> dict:
        cities = await self._cities_from_request(ctx)
        if not cities:
            return {"reply": "🌤️ 您想查询哪个城市的天气？例如「北京天气」「三亚周末天气」。",
                    "data": {"weather": []}}
        agent = WeatherAgent(ctx)
        weather = await agent.run(cities)
        reply = render_weather(weather) + "\n\n" + self._weather_advice(weather)
        return {"reply": reply, "data": {"weather": weather}}

    @staticmethod
    def _weather_advice(weather: list[dict]) -> str:
        lines = ["### 💡 出行建议"]
        rainy = [w for w in weather if "雨" in w.get("condition", "")]
        hot = [w for w in weather if (w.get("t_max") or 0) >= 30]
        cold = [w for w in weather if (w.get("t_max") or 99) <= 10]
        if rainy:
            lines.append(f"- {'、'.join(w['city'] for w in rainy)} 有降水，请携带雨具")
        if hot:
            lines.append(f"- {'、'.join(w['city'] for w in hot)} 气温较高，注意防晒补水")
        if cold:
            lines.append(f"- {'、'.join(w['city'] for w in cold)} 气温较低，注意保暖")
        if not rainy and not hot and not cold:
            lines.append("- 天气整体适宜出行，早晚注意温差")
        return "\n".join(lines)

    async def _hotel_flow(self, ctx: AgentContext, emit: EmitFn) -> dict:
        cities = await self._cities_from_request(ctx)
        if not cities:
            return {"reply": "🏨 您想查询哪个城市的酒店？例如「推荐丽江适合情侣的酒店」。",
                    "data": {"hotels": []}}
        spec = TripSpec()
        for kw, level in [("穷游", "经济"), ("经济", "经济"), ("性价比", "经济"),
                          ("舒适", "舒适"), ("中等", "舒适"),
                          ("豪华", "豪华"), ("高端", "豪华"), ("奢华", "豪华"), ("五星", "豪华")]:
            if kw in ctx.request:
                spec.budget_level = level
                break
        pref_kws = ["情侣", "亲子", "海景", "古镇", "市中心", "江景", "雪山景观"]
        spec.preferences = [k for k in pref_kws if k in ctx.request]
        agent = HotelAgent(ctx)
        hotels = await agent.run(cities, spec)
        reply = render_hotels(hotels) + "\n\n> 💡 需要更精确的推荐？可以告诉我预算档位（经济/舒适/豪华）和偏好（海景、亲子、古镇等）。"
        return {"reply": reply, "data": {"hotels": hotels}}

    async def _attraction_flow(self, ctx: AgentContext, emit: EmitFn) -> dict:
        cities = await self._cities_from_request(ctx)
        if not cities:
            return {"reply": "🏔️ 您想查询哪个城市的景点？例如「北京有哪些必去景点」。",
                    "data": {"attractions": []}}
        spec = TripSpec()
        pref_kws = ["自然风光", "看海", "海边", "海岛", "雪山", "古镇", "古城", "美食",
                    "亲子", "情侣", "文艺", "摄影", "徒步", "登山", "博物馆", "夜景", "乐园", "历史"]
        spec.preferences = [k for k in pref_kws if k in ctx.request]
        agent = AttractionAgent(ctx)
        attractions = await agent.run(cities, spec)
        reply = render_attractions(attractions) + "\n\n> 💡 可以告诉我对景点的偏好（自然风光、亲子、历史人文等），推荐会更精准。"
        return {"reply": reply, "data": {"attractions": attractions}}

    async def _feedback_flow(self, ctx: AgentContext, emit: EmitFn) -> dict:
        # 支持对话式反馈：解析评分/意见
        agent = FeedbackAgent(ctx)
        rating = 5
        m = re.search(r"(\d)\s*分", ctx.request)
        if m:
            rating = int(m.group(1))
        elif re.search(r"不满意|太差|失望|吐槽", ctx.request):
            rating = 2
        elif re.search(r"还行|一般|可以", ctx.request):
            rating = 4
        tags = [t for t in ["酒店太贵", "路线太赶", "景点一般", "交通", "天气", "美食", "排队", "价格"] if t in ctx.request]
        result = await agent.process(ctx.user_id, rating, ctx.request, tags)
        reply = await agent.acknowledge(rating, result["lessons"])
        return {"reply": reply, "data": {"feedback": result}}

    async def _greeting_flow(self, ctx: AgentContext, emit: EmitFn) -> dict:
        reply = (
            "👋 您好！我是**旅行星球**的旅行规划总指挥，可以为您提供：\n\n"
            "| 能力 | 示例 |\n| --- | --- |\n"
            "| 🗺️ 行程规划 | 帮我规划云南昆明-大理-丽江 5 日游 |\n"
            "| ☀️ 天气查询 | 北京明天天气怎么样 |\n"
            "| 🏨 酒店推荐 | 推荐三亚适合亲子的酒店 |\n"
            "| 🏔️ 景点推荐 | 成都必去的景点 |\n"
            "| 💰 付费下单 | 方案满意后我会主动询问是否下单 |\n"
            "| 📝 反馈学习 | 上次行程太赶了（我会记住并改进）|\n\n"
            "由 8 位专家智能体协作完成：全程 RAG 知识检索 + 长期记忆 + 地理就近路线编排，"
            "路线保证景点不重复、酒店贴近景点群。"
        )
        return {"reply": reply, "data": {}}

    async def _general_flow(self, ctx: AgentContext, emit: EmitFn) -> dict:
        # RAG 参考 + LLM（或离线模板）回答
        kb = get_knowledge_base()
        docs = await kb.retrieve(ctx.request, k=3)
        llm = get_llm_client()
        context_note = ""
        if docs:
            refs = "\n".join(f"- {d.text[:180]}" for d in docs[:3])
            context_note = f"\n\n### 📚 知识库参考\n{refs}"

        if llm.mode == "llm":
            messages = ctx.packet.to_messages(ctx.request)
            reply = await llm.chat(messages, temperature=0.4, max_tokens=800)
        else:
            reply = llm.chat([{"role": "user", "content": ctx.request}])
        return {"reply": reply + context_note, "data": {"knowledge": [d.text for d in docs]}}

    # ==================== 工具方法 ====================
    def _make_summary(self, spec: TripSpec, cities: list[str]) -> str:
        parts = [f"本方案串联 {' → '.join(cities)}，共 {spec.days} 天"]
        if spec.preferences:
            parts.append(f"，围绕「{'、'.join(spec.preferences[:3])}」设计")
        if spec.travelers:
            parts.append(f"，适合{spec.travelers}")
        parts.append("。每天 2-3 个核心景点 + 特色美食 + 高性价比住宿，节奏松弛有度。")
        return "".join(parts)

    def _make_tips(self, spec: TripSpec, weather: list[dict]) -> list[str]:
        tips = [
            "热门景点建议提前 1-3 天线上预约购票",
            "城际之间优先高铁，时间灵活且准点率高",
            "住宿选择靠近地铁/景区入口，节省通勤时间",
        ]
        if spec.start_date:
            tips.append(f"出行日期 {spec.start_date}，请提前关注航班/火车票价格")
        rainy = [w for w in weather if "雨" in w.get("condition", "")]
        if rainy:
            tips.append(f"{'、'.join(w['city'] for w in rainy)} 近期有降水，备好雨具并预留室内备选")
        if spec.travelers and "亲" in spec.travelers:
            tips.append("亲子出行建议控制单日步行量，预留午休时间")
        if spec.budget_level == "经济":
            tips.append("经济出行建议：青旅/民宿 + 公共交通 + 平价餐饮，人均可控制在 300 元/天内")
        return tips[:5]

    async def _save_trip(self, ctx: AgentContext, plan: dict) -> int | None:
        try:
            from app.db.database import SessionLocal
            from app.db.models import Trip

            async with SessionLocal() as session:
                trip = Trip(
                    user_id=ctx.user_id,
                    title=plan.get("title", "旅行方案"),
                    request=ctx.request,
                    cities=",".join(plan.get("cities", [])),
                    days=plan.get("days", 1),
                    budget=plan.get("budget_range", ""),
                    plan_json=json.dumps(plan, ensure_ascii=False),
                    markdown=plan.get("markdown", ""),
                )
                session.add(trip)
                await session.commit()
                await session.refresh(trip)
                return trip.id
        except Exception as e:
            logger.warning("保存行程失败: %s", e)
            return None


_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
