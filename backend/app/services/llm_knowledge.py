"""LLM 长尾城市知识兜底：知识库与高德都没有数据时，让 LLM 生成景点/酒店参考数据。

触发条件（由 MCP 工具兜底链调用）：本地知识库无该城市数据 且 高德 Key 未配置/无结果。
产出标注 source="llm"，前端显示「AI 参考」徽标；价格/坐标为估算值，描述中注明仅供参考。
带 1 小时内存缓存，避免同一城市重复调用 LLM。
"""
from __future__ import annotations

import logging
import time

from app.prompts import ATTRACTION_GEN_SYSTEM, HOTEL_GEN_SYSTEM
from app.services.llm import get_llm_client

logger = logging.getLogger(__name__)

_CACHE: dict[tuple, tuple[float, list[dict]]] = {}
_CACHE_TTL = 3600  # 秒


def _cache_get(key: tuple) -> list[dict] | None:
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    if hit:
        _CACHE.pop(key, None)
    return None


def _cache_set(key: tuple, value: list[dict]) -> None:
    if len(_CACHE) > 200:  # 简单防膨胀
        _CACHE.clear()
    _CACHE[key] = (time.monotonic(), value)


async def llm_attractions(city: str, interests: list[str] | None = None,
                          n: int = 6) -> list[dict] | None:
    """LLM 生成城市景点参考数据；LLM 未配置或生成失败返回 None。"""
    llm = get_llm_client()
    if llm.mode != "llm":
        return None
    key = ("attr", city, tuple(interests or []), n)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    user = (
        f"城市：{city}\n"
        f"兴趣偏好：{'、'.join(interests[:4]) if interests else '综合（覆盖最经典景点）'}\n"
        f"请推荐 {n} 个景点。"
    )
    try:
        parsed = await llm.chat_json(
            [
                {"role": "system", "content": ATTRACTION_GEN_SYSTEM},
                {"role": "user", "content": user},
            ]
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM 景点生成失败 %s: %s", city, e)
        return None
    items = parsed.get("attractions") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return None

    out: list[dict] = []
    for it in items[:n]:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        try:
            price = max(0, int(float(it.get("price") or 0)))
        except (TypeError, ValueError):
            price = 0
        loc = None
        try:
            if it.get("lat") is not None and it.get("lon") is not None:
                loc = {"lat": round(float(it["lat"]), 4), "lon": round(float(it["lon"]), 4)}
        except (TypeError, ValueError):
            loc = None
        desc = str(it.get("desc") or "").strip()[:60]
        out.append(
            {
                "name": str(it["name"]).strip()[:40],
                "city": city,
                "price": price,
                "duration": str(it.get("duration") or "2-3小时")[:10],
                "tags": [str(t).strip()[:12] for t in (it.get("tags") or [])[:3]],
                "desc": (desc + "｜" if desc else "") + "AI 整理，门票以景区公示为准",
                "location": loc,
                "match_interests": [],
                "source": "llm",
            }
        )
    if not out:
        return None
    _cache_set(key, out)
    return out


async def llm_hotels(city: str, budget: str = "", keywords: list[str] | None = None,
                     n: int = 3) -> list[dict] | None:
    """LLM 生成城市酒店参考数据；LLM 未配置或生成失败返回 None。"""
    llm = get_llm_client()
    if llm.mode != "llm":
        return None
    key = ("hotel", city, budget, tuple(keywords or []), n)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    user = (
        f"城市：{city}\n"
        f"预算档位：{budget or '不限（覆盖豪华/舒适/经济各一）'}\n"
        f"偏好：{'、'.join(keywords[:4]) if keywords else '交通方便'}\n"
        f"请推荐 {n} 家住宿。"
    )
    try:
        parsed = await llm.chat_json(
            [
                {"role": "system", "content": HOTEL_GEN_SYSTEM},
                {"role": "user", "content": user},
            ]
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM 酒店生成失败 %s: %s", city, e)
        return None
    items = parsed.get("hotels") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return None

    out: list[dict] = []
    for it in items[:n]:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        try:
            price = max(0, int(float(it.get("price") or 0)))
        except (TypeError, ValueError):
            price = 400
        try:
            rating = min(5.0, max(3.5, float(it.get("rating") or 4.5)))
        except (TypeError, ValueError):
            rating = 4.5
        loc = None
        try:
            if it.get("lat") is not None and it.get("lon") is not None:
                loc = {"lat": round(float(it["lat"]), 4), "lon": round(float(it["lon"]), 4)}
        except (TypeError, ValueError):
            loc = None
        desc = str(it.get("desc") or "").strip()[:50]
        out.append(
            {
                "name": str(it["name"]).strip()[:40],
                "city": city,
                "price": price,
                "rating": round(rating, 1),
                "tags": [str(t).strip()[:12] for t in (it.get("tags") or ["舒适"])[:4]],
                "desc": (desc + "｜" if desc else "") + "AI 参考，请以预订平台为准",
                "address": str(it.get("address") or "").strip()[:60],
                "location": loc,
                "match_tags": [k for k in (keywords or []) if k in str(it)],
                "budget_level": next(
                    (label for label, rng in (("经济", (0, 300)), ("舒适", (300, 800)), ("豪华", (800, 10**9)))
                     if rng[0] <= price < rng[1]),
                    "综合",
                ),
                "source": "llm",
            }
        )
    if not out:
        return None
    _cache_set(key, out)
    return out
