"""高德地图（Amap）开放平台服务：真实酒店 POI 检索 + 地理编码 + 周边搜索。

- 申请 Key：https://console.amap.com/dev/key/app（「Web服务」类型 Key）
- 配置方式：.env 的 AMAP_API_KEY，或前端「设置」页运行时保存（即时生效）
- 未配置 Key 或调用失败：返回 None，调用方自动回退本地知识库数据
- 坐标系：高德返回 GCJ-02，直接与本地数据（同为 GCJ-02 口径）混合使用，误差可忽略

主要接口（v5）：
  /v5/place/text   关键字搜索（酒店 types=100000，支持 show_fields=business 取评分/人均）
  /v5/place/around 周边搜索（按景点群中心找就近酒店）
  /v5/geocode/geo  地理编码（城市 → 中心点坐标）
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.services.runtime_config import resolve_amap_key

logger = logging.getLogger(__name__)

AMAP_BASE = "https://restapi.amap.com"
PLACE_TIMEOUT = 8.0
_CACHE_TTL = 600  # 检索缓存秒数（防止触发 QPS 限流）

# 预算档位 → 人均房价区间（高德 business.cost 为人均参考价）
_BUDGET_PRICE_RANGE = {"经济": (0, 300), "舒适": (300, 800), "豪华": (800, 10**9)}

# 用户兴趣词 → 高德 POI 检索词（用于长尾城市的兴趣化景点搜索）
_INTEREST_TERMS = {
    "亲子": "乐园", "带娃": "亲子", "历史文化": "博物馆", "历史": "博物馆",
    "博物馆": "博物馆", "美食": "美食", "古镇": "古镇", "古城": "古城",
    "文艺": "艺术", "摄影": "摄影", "看海": "海滨", "海边": "海滨", "海岛": "岛",
    "登山": "山", "徒步": "山", "雪山": "雪山", "温泉": "温泉", "乐园": "乐园",
    "动物园": "动物园", "植物园": "植物园", "夜景": "夜景", "自然风光": "景区",
    "赏花": "公园", "避暑": "公园", "潜水": "潜水", "漂流": "漂流", "滑雪": "滑雪",
}


def _loc_to_dict(location: str) -> dict[str, float] | None:
    """"lng,lat" → {"lat": ..., "lon": ...}"""
    try:
        lon_s, lat_s = location.split(",")
        return {"lat": round(float(lat_s), 6), "lon": round(float(lon_s), 6)}
    except (ValueError, AttributeError):
        return None


class AmapService:
    def __init__(self):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    def is_ready(self) -> bool:
        """是否配置了高德 Key（未配置时调用方回退本地数据）。"""
        return bool(resolve_amap_key())

    # ---------- 基础 ----------
    async def _get(self, path: str, params: dict[str, Any]) -> dict | None:
        key = resolve_amap_key()
        if not key:
            return None
        params = {"key": key, **params}
        cache_key = path + str(sorted(params.items()))
        now = time.monotonic()
        hit = self._cache.get(cache_key)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]

        async with self._lock:
            hit = self._cache.get(cache_key)
            if hit and time.monotonic() - hit[0] < _CACHE_TTL:
                return hit[1]
            try:
                async with httpx.AsyncClient(timeout=PLACE_TIMEOUT) as client:
                    resp = await client.get(f"{AMAP_BASE}{path}", params=params)
                    data = resp.json()
            except Exception as e:  # noqa: BLE001
                logger.warning("高德接口调用失败 %s: %s", path, e)
                return None
            if str(data.get("status")) != "1":
                logger.warning("高德接口返回失败 %s: %s", path, data.get("info"))
                return None
            self._cache[cache_key] = (time.monotonic(), data)
            return data

    # ---------- 地理编码 ----------
    async def geocode(self, city: str) -> dict[str, float] | None:
        """城市名 → 中心点坐标 {"lat", "lon"}。"""
        data = await self._get("/v5/geocode/geo", {"address": city})
        try:
            loc = data["geocodes"][0]["location"]
            return _loc_to_dict(loc)
        except (TypeError, KeyError, IndexError):
            return None

    # ---------- 酒店检索 ----------
    async def search_hotels(
        self,
        city: str,
        budget: str = "",
        keywords: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict] | None:
        """按城市搜索真实酒店 POI。失败/无 Key 返回 None（调用方回退本地数据）。"""
        kw = "酒店"
        if keywords:
            kw = f"酒店 {keywords[0]}" if len(keywords) == 1 else "酒店"
        data = await self._get(
            "/v5/place/text",
            {
                "keywords": kw,
                "city": city,
                "citylimit": "true",
                "types": "100000",  # 住宿服务
                "page_size": min(25, max(10, top_k * 4)),
                "show_fields": "business,photos",
            },
        )
        if data is None:
            return None
        pois = data.get("pois") or []
        if not pois:
            return None

        kws = [k for k in (keywords or []) if k]
        budget_range = next((r for name, r in _BUDGET_PRICE_RANGE.items() if name in (budget or "")), None)

        hotels: list[dict] = []
        for poi in pois:
            business = poi.get("business") or {}
            name = poi.get("name", "")
            rating = _to_float(business.get("rating"))
            cost = _to_float(business.get("cost"))
            price = cost if cost and cost > 0 else _estimate_price(name, poi.get("type", ""))
            location = _loc_to_dict(poi.get("location", ""))
            tag_set = {t for t in poi.get("type", "").split(";") if t and t not in ("住宿服务",)}
            if kws:
                matched = [k for k in kws if k in name or any(k in t for t in tag_set)]
            else:
                matched = []
            hotels.append(
                {
                    "name": name,
                    "city": city,
                    "price": int(round(price)),
                    "rating": rating if rating else 4.5,
                    "tags": sorted(tag_set)[:4] or ["酒店"],
                    "desc": _desc_of(poi),
                    "address": poi.get("address", ""),
                    "location": location,
                    "budget_level": next(
                        (label for label, (lo, hi) in _BUDGET_PRICE_RANGE.items() if lo <= price < hi), "综合"
                    ),
                    "match_tags": matched,
                    "source": "amap",
                    "_score": round(
                        (rating if rating else 4.5) * 10
                        + len(matched) * 4
                        + (3 if budget_range and budget_range[0] <= price < budget_range[1] else 0),
                        1,
                    ),
                }
            )

        if budget_range:
            # 预算过滤：有真实人均价的严格过滤，估价酒店降权后保留
            in_range = [h for h in hotels if budget_range[0] <= h["price"] < budget_range[1]]
            if in_range:
                hotels = in_range
        hotels.sort(key=lambda h: h["_score"], reverse=True)
        for h in hotels:
            h.pop("_score", None)
        return hotels[:top_k]

    # ---------- 周边搜索 ----------
    async def search_hotels_near(
        self, lat: float, lon: float, city: str = "", budget: str = "", top_k: int = 5
    ) -> list[dict] | None:
        """按坐标周边搜索酒店（用于「就近景点群」选酒店）。"""
        params: dict[str, Any] = {
            "location": f"{lon},{lat}",
            "keywords": "酒店",
            "types": "100000",
            "radius": 5000,
            "page_size": 15,
            "show_fields": "business",
        }
        if city:
            params["city"] = city
        data = await self._get("/v5/place/around", params)
        if data is None:
            return None
        pois = data.get("pois") or []
        if not pois:
            return None
        hotels: list[dict] = []
        for poi in pois:
            business = poi.get("business") or {}
            name = poi.get("name", "")
            rating = _to_float(business.get("rating"))
            cost = _to_float(business.get("cost"))
            price = cost if cost and cost > 0 else _estimate_price(name, poi.get("type", ""))
            hotels.append(
                {
                    "name": name,
                    "city": city or poi.get("cityname", ""),
                    "price": int(round(price)),
                    "rating": rating if rating else 4.5,
                    "tags": ["酒店"],
                    "desc": _desc_of(poi),
                    "address": poi.get("address", ""),
                    "location": _loc_to_dict(poi.get("location", "")),
                    "budget_level": next(
                        (label for label, (lo, hi) in _BUDGET_PRICE_RANGE.items() if lo <= price < hi), "综合"
                    ),
                    "source": "amap",
                }
            )
        budget_range = next((r for name, r in _BUDGET_PRICE_RANGE.items() if name in (budget or "")), None)
        if budget_range:
            in_range = [h for h in hotels if budget_range[0] <= h["price"] < budget_range[1]]
            if in_range:
                hotels = in_range
        hotels.sort(key=lambda h: h["rating"], reverse=True)
        return hotels[:top_k]

    # ---------- 景点检索（长尾城市兜底） ----------
    async def search_attractions(
        self, city: str, interests: list[str] | None = None, top_k: int = 5
    ) -> list[dict] | None:
        """按城市检索风景名胜 POI（types=110000），兴趣词做第二路检索融合。

        用于本地知识库未覆盖的城市；失败/无 Key 返回 None（调用方回退或提示）。
        """
        base = await self._get(
            "/v5/place/text",
            {"city": city, "citylimit": "true", "types": "110000", "page_size": 25,
             "show_fields": "business"},
        )
        if base is None:
            return None
        pois = base.get("pois") or []
        if not pois:
            return None

        # 兴趣词第二路检索（最多 2 路），补充主题景点
        terms = []
        for it in (interests or []):
            term = _INTEREST_TERMS.get(it, it)
            if term and term not in terms:
                terms.append(term)
        merged: dict[str, dict] = {}
        for poi in pois:
            merged[poi.get("name", "")] = poi
        for term in terms[:2]:
            extra = await self._get(
                "/v5/place/text",
                {"keywords": term, "city": city, "citylimit": "true", "types": "110000",
                 "page_size": 10, "show_fields": "business"},
            )
            for poi in (extra or {}).get("pois") or []:
                merged.setdefault(poi.get("name", ""), poi)

        kws = [t for t in (terms or []) if t]
        scored: list[dict] = []
        for name, poi in merged.items():
            if not name:
                continue
            business = poi.get("business") or {}
            poi_type = poi.get("type", "")
            type_tail = [t for t in poi_type.split(";") if t and t != "风景名胜"]
            rating = _to_float(business.get("rating"))
            cost = _to_float(business.get("cost"))
            matched = [k for k in kws if k in name or any(k in t for t in type_tail)]
            addr = poi.get("address", "") or ""
            desc = f"{addr}（门票以景区公示为准）" if addr else f"{type_tail[-1] if type_tail else '景点'}（门票以景区公示为准）"
            scored.append(
                {
                    "name": name,
                    "city": city,
                    "price": int(cost) if cost else 0,
                    "duration": _estimate_duration(name, poi_type),
                    "tags": list(dict.fromkeys((type_tail[-2:] or ["景点"]) + matched)),
                    "desc": desc,
                    "location": _loc_to_dict(poi.get("location", "")),
                    "address": addr,
                    "match_interests": matched,
                    "source": "amap",
                    "_score": round((rating if rating else 4.2) * 10 + len(matched) * 4, 1),
                }
            )
        scored.sort(key=lambda a: a["_score"], reverse=True)
        result = scored[:top_k]
        for a in result:
            a.pop("_score", None)
        return result


def _estimate_duration(name: str, poi_type: str) -> str:
    """POI 名称/类目 → 建议游玩时长（粗略估计）。"""
    text = name + poi_type
    if any(k in text for k in ("国家森林公园", "古镇", "古城", "度假区", "风景区", "山", "湖", "岛", "遗址")):
        return "半天"
    return "2-3小时"


def _to_float(v: Any) -> float | None:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _estimate_price(name: str, poi_type: str) -> float:
    """高德部分 POI 缺少人均价时，按名称/类目估算（结果标注为估价口径）。"""
    text = name + poi_type
    if any(w in text for w in ("五星级", "豪华", "国际大酒店", "W酒店", "洲际", "瑞吉", "四季", "丽思")):
        return 1000
    if "民宿" in text or "客栈" in text or "公寓" in text:
        return 220
    if "青年旅舍" in text or "青旅" in text or "旅舍" in text:
        return 100
    return 450


def _desc_of(poi: dict) -> str:
    addr = poi.get("address", "") or ""
    pname = poi.get("pname", "")
    cityname = poi.get("cityname", "")
    region = " · ".join(x for x in (pname, cityname) if x and x not in addr)
    return f"{region} {addr}".strip() or "高德地图 POI"


_amap_service: AmapService | None = None


def get_amap_service() -> AmapService:
    global _amap_service
    if _amap_service is None:
        _amap_service = AmapService()
    return _amap_service
