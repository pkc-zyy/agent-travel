"""酒店/景点/城市 数据服务：读取知识库 JSON，按城市、预算、关键词过滤排序。"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.config import get_settings

_BUDGET_LEVELS = {
    "经济": (0, 250, "经济型"),
    "舒适": (250, 700, "舒适型"),
    "豪华": (700, 10**9, "豪华型"),
}


def _load_json(name: str) -> list[dict]:
    path = get_settings().knowledge_dir / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def get_city_meta() -> dict[str, dict]:
    path = get_settings().knowledge_dir / "city_meta.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def get_all_hotels() -> list[dict]:
    return _load_json("hotels.json")


@lru_cache
def get_all_attractions() -> list[dict]:
    return _load_json("attractions.json")


def _budget_range(budget: str | None) -> tuple[int, int, str] | None:
    if not budget:
        return None
    for key, (lo, hi, label) in _BUDGET_LEVELS.items():
        if key in budget:
            return lo, hi, label
    return None


def _tag_match(tags: list[str], keywords: list[str]) -> int:
    return sum(1 for k in keywords if any(k in t for t in tags))


class HotelService:
    """酒店推荐：城市过滤 + 预算过滤 + 关键词打分，返回 Top N。"""

    def search(self, city: str | None = None, budget: str | None = None,
               keywords: list[str] | None = None, top_k: int = 3) -> list[dict]:
        keywords = [k for k in (keywords or []) if k]
        hotels = get_all_hotels()
        if city:
            hotels = [h for h in hotels if h["city"] == city]

        br = _budget_range(budget)
        if br:
            lo, hi, label = br
            hotels = [h for h in hotels if lo <= h["price"] <= hi]
            budget_label = label
        else:
            budget_label = "综合"

        scored: list[dict] = []
        for h in hotels:
            score = h["rating"] * 10 + _tag_match(h.get("tags", []), keywords) * 3
            item = dict(h)
            item["_score"] = round(score, 1)
            scored.append(item)
        scored.sort(key=lambda h: h["_score"], reverse=True)

        result = []
        for h in scored[:top_k]:
            matched = [k for k in keywords if any(k in t for t in h.get("tags", []))]
            result.append(
                {
                    "name": h["name"],
                    "city": h["city"],
                    "price": h["price"],
                    "rating": h["rating"],
                    "tags": h.get("tags", []),
                    "desc": h.get("desc", ""),
                    "address": h.get("address", ""),
                    "location": h.get("location"),
                    "budget_level": budget_label,
                    "match_tags": matched,
                    "score": h["_score"],
                    "source": "local",
                }
            )
        return result


class AttractionService:
    """景点推荐：城市过滤 + 兴趣关键词打分。"""

    def search(self, city: str | None = None, interests: list[str] | None = None,
               top_k: int = 5) -> list[dict]:
        interests = [i for i in (interests or []) if i]
        attrs = get_all_attractions()
        if city:
            attrs = [a for a in attrs if a["city"] == city]

        scored: list[dict] = []
        for a in attrs:
            item = dict(a)
            item["_score"] = _tag_match(a.get("tags", []), interests) * 2
            scored.append(item)
        scored.sort(key=lambda a: a["_score"], reverse=True)

        result = []
        for a in scored[:top_k]:
            matched = [i for i in interests if any(i in t for t in a.get("tags", []))]
            result.append(
                {
                    "name": a["name"],
                    "city": a["city"],
                    "price": a["price"],
                    "duration": a.get("duration", ""),
                    "tags": a.get("tags", []),
                    "desc": a.get("desc", ""),
                    "location": a.get("location"),
                    "match_interests": matched,
                    "source": "local",
                }
            )
        return result


@lru_cache
def get_hotel_service() -> HotelService:
    return HotelService()


@lru_cache
def get_attraction_service() -> AttractionService:
    return AttractionService()


def get_city_info(city: str) -> dict[str, Any]:
    meta = get_city_meta().get(city)
    if meta is None:
        # 精选库之外：查全国城市坐标表（供天气定位与距离估算）
        from app.services.cities_cn import get as cn_city_get

        ext = cn_city_get(city)
        if ext:
            return {
                "name": city,
                "province": ext.get("province", ""),
                "lat": ext.get("lat"),
                "lon": ext.get("lon"),
                "desc": "",
                "tags": [],
                "known_for": [],
                "cuisine": [],
                "best_season": "",
            }
        return {"name": city, "desc": "", "tags": [], "known_for": [], "cuisine": []}
    return {
        "name": city,
        "province": meta.get("province", ""),
        "lat": meta.get("lat"),
        "lon": meta.get("lon"),
        "desc": meta.get("desc", ""),
        "tags": meta.get("tags", []),
        "known_for": meta.get("known_for", []),
        "cuisine": meta.get("cuisine", []),
        "best_season": meta.get("best_season", ""),
    }


def known_cities() -> list[str]:
    """系统可识别的全部城市：精选知识库 25 城 + 全国主要城市坐标表。"""
    from app.services.cities_cn import CITIES_CN

    cities = list(get_city_meta().keys())
    cities += [c for c in CITIES_CN if c not in set(cities)]
    return cities


def curated_cities() -> list[str]:
    """精选知识库城市（25 城，含完整景点/酒店/指南数据）。"""
    return list(get_city_meta().keys())
