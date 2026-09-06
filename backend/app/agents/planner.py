"""行程规划师 Agent：解析用户需求 → 制定行程框架 → 分配任务 → 整合最终方案。"""
from __future__ import annotations

import re
from datetime import date, timedelta

from app.agents.base import AgentContext, BaseAgent, TripSpec
from app.prompts import PLANNER_PARSE_SYSTEM
from app.services.catalog import get_city_info, known_cities

_DAY_RE = re.compile(r"(\d{1,2})\s*[天日]")
_BUDGET_RE = re.compile(r"人均\s*(\d{2,5})(?:\s*[-~至到]\s*(\d{2,5}))?\s*元")
_START_RE = re.compile(r"(今天|明天|后天|下周[一二三四五六日天]?|(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?))")
_TRAVELERS_RE = re.compile(r"(一个人|两人|两个人|情侣|蜜月|亲子|带[娃孩老人爸妈]|家庭|和[^，。；]{1,6}(?:一起|同行))")

_BUDGET_KEYWORDS = [
    ("穷游", "经济"), ("经济", "经济"), ("性价比", "经济"), ("省钱", "经济"),
    ("舒适", "舒适"), ("中等", "舒适"), ("中档", "舒适"),
    ("豪华", "豪华"), ("高端", "豪华"), ("奢华", "豪华"), ("五星", "豪华"),
]

_PREF_KEYWORDS = [
    "自然风光", "看海", "海边", "海岛", "雪山", "古镇", "古城", "美食", "吃货",
    "亲子", "带孩子", "带娃", "情侣", "蜜月", "文艺", "摄影", "徒步", "登山",
    "休闲", "慢节奏", "购物", "历史文化", "博物馆", "夜景", "潜水", "露营",
    "温泉", "漂流", "动物园", "乐园", "迪士尼", "避暑", "赏花",
]


def _find_cities(text: str) -> list[str]:
    """在文本中按长度优先匹配已知城市。"""
    known = sorted(known_cities(), key=len, reverse=True)
    found: list[str] = []
    rest = text
    for city in known:
        if city in rest:
            found.append(city)
            rest = rest.replace(city, " ", 1)
    return found


class PlannerAgent(BaseAgent):
    name = "行程规划师"
    emoji = "🧭"
    role = "解析用户需求，设计整体行程框架并分配任务"

    async def parse_request(self, text: str) -> TripSpec:
        await self.emit("running", "正在解析您的需求（目的地 / 天数 / 预算 / 偏好）…")
        spec = TripSpec()

        spec.cities = _find_cities(text)
        if not spec.cities:
            # 从长期记忆中找目的地
            for mem in (self.ctx.packet.memories if self.ctx.packet else []):
                for c in known_cities():
                    if c in mem.get("content", "") and c not in spec.cities:
                        spec.cities.append(c)
                if spec.cities:
                    break

        m = _DAY_RE.search(text)
        if m:
            spec.days = min(14, max(1, int(m.group(1))))

        m = _BUDGET_RE.search(text)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2)) if m.group(2) else None
            spec.budget = f"人均{lo}" + (f"-{hi}元" if hi else "元")
            spec.budget_level = (
                "经济" if hi is not None and hi <= 3000 else
                "豪华" if lo >= 8000 else "舒适"
            )
        else:
            for kw, level in _BUDGET_KEYWORDS:
                if kw in text:
                    spec.budget_level = level
                    spec.budget = f"{level}型"
                    break

        spec.preferences = [k for k in _PREF_KEYWORDS if k in text]

        m = _TRAVELERS_RE.search(text)
        if m:
            spec.travelers = m.group(1)

        m = _START_RE.search(text)
        if m:
            token = m.group(1)
            if token == "今天":
                spec.start_date = date.today().isoformat()
            elif token == "明天":
                spec.start_date = (date.today() + timedelta(days=1)).isoformat()
            elif token == "后天":
                spec.start_date = (date.today() + timedelta(days=2)).isoformat()
            elif "下周" in token:
                days_ahead = 7 - date.today().weekday()
                spec.start_date = (date.today() + timedelta(days=days_ahead)).isoformat()
            else:
                spec.start_date = token.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")

        # LLM 增强解析（可选）
        from app.services.llm import get_llm_client

        llm = get_llm_client()
        if llm.mode == "llm":
            try:
                parsed = await llm.chat_json(
                    [
                        {"role": "system", "content": PLANNER_PARSE_SYSTEM},
                        {"role": "user", "content": text[:600]},
                    ]
                )
                if parsed:
                    if isinstance(parsed.get("cities"), list) and parsed["cities"]:
                        validated = await self._validate_cities([str(c) for c in parsed["cities"]])
                        if validated:
                            spec.cities = validated
                    if isinstance(parsed.get("days"), int) and 1 <= parsed["days"] <= 14:
                        spec.days = parsed["days"]
                    if parsed.get("budget"):
                        spec.budget = str(parsed["budget"])
                    if isinstance(parsed.get("preferences"), list):
                        spec.preferences = list(dict.fromkeys(spec.preferences + [str(p) for p in parsed["preferences"]]))
                    if parsed.get("travelers"):
                        spec.travelers = str(parsed["travelers"])
                    if parsed.get("start_date"):
                        spec.start_date = str(parsed["start_date"])
            except Exception:
                pass

        if not spec.cities:
            spec.needs_more_info = "请告诉我您想去哪个城市或地区（已支持全国主要城市，如「温州」「敦煌」「景德镇」，也可多城联游如「昆明-大理-丽江」）"
        elif spec.days < len(spec.cities):
            spec.days = len(spec.cities)
            spec.needs_more_info = ""
        await self.emit("done", f"需求解析完成：{len(spec.cities)} 个城市，{spec.days} 天")
        return spec

    async def _validate_cities(self, names: list[str]) -> list[str]:
        """校验 LLM 解析出的城市：
        1. 已知城市（精选 25 城 + 全国主要城市表）直接通过；
        2. 其余城市在高德可用时经地理编码验证；
        3. 都不可用时信任 LLM 提取结果（解析提示词已约束只输出真实中国城市）。
        """
        from app.services.amap import get_amap_service

        known = set(known_cities())
        amap = get_amap_service()
        out: list[str] = []
        for name in names:
            name = name.strip()
            if not name or name in out or len(name) > 12:
                continue
            if name in known:
                out.append(name)
                continue
            if amap.is_ready():
                try:
                    loc = await amap.geocode(name)
                except Exception:  # noqa: BLE001
                    loc = None
                if loc:
                    out.append(name)
                    continue
            # 长尾兜底：LLM 提取的城市名直接接受（下游用 LLM/高德补数据）
            out.append(name)
        return out

    # ---------- 框架 ----------
    def build_framework(self, spec: TripSpec) -> list[tuple[int, str]]:
        """将天数分配到城市序列：首尾城市各 1 天，其余均分给中间城市。"""
        cities = spec.cities
        n = len(cities)
        days = spec.days
        if n == 1:
            return [(i + 1, cities[0]) for i in range(days)]
        counts = [1] * n
        remain = days - n
        if remain > 0:
            mid = max(1, n - 2)
            for i in range(1, n - 1):
                add = remain // mid
                counts[i] += add
                remain -= add
            counts[-1] += remain
        result: list[tuple[int, str]] = []
        for i, city in enumerate(cities):
            for d in range(counts[i]):
                result.append((len(result) + 1, city))
        return result

    def city_day_titles(self) -> dict[str, str]:
        return {
            "昆明": "春城花都漫步", "大理": "风花雪月环洱海", "丽江": "古城雪山慢生活",
            "成都": "熊猫与美食之都", "重庆": "8D魔幻山城体验", "北京": "古都文化之旅",
            "上海": "摩登都市漫游", "杭州": "江南水乡诗意行", "西安": "千年古都寻梦",
            "三亚": "热带海岛度假", "厦门": "文艺海岛慢时光", "青岛": "红瓦绿树海滨行",
        }

    async def integrate(self, plan: dict) -> str:
        """整合生成最终方案 Markdown。"""
        from app.agents.composer import render_plan

        await self.emit("done", "正在整合专家信息，生成最终方案…")
        return render_plan(plan)
