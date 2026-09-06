"""地理路由服务：坐标距离计算 + 就近路线优化。

解决行程规划两大问题：
1. 景点重复 —— 调度层保证同一景点全程只排一次（见 orchestrator._build_schedule）
2. 距离过大 —— 每天从酒店出发做最近邻链式路由；酒店按「贴近景点群」择优

坐标说明：数据与高德 POI 同为 GCJ-02 口径，haversine 结果为直线距离（展示误差可忽略），
标注为「直线距离/车程约 1.3 倍」估算。
"""
from __future__ import annotations

import math
from typing import Any, Iterable

_EARTH_RADIUS_KM = 6371.0
# 直线距离 → 市内车程的粗略系数（绕路/路网折减）
DRIVE_FACTOR = 1.35


def loc_of(item: dict) -> tuple[float, float] | None:
    """从酒店/景点字典取 (lat, lon)，无坐标返回 None。"""
    loc = item.get("location") or {}
    lat, lon = loc.get("lat"), loc.get("lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def haversine_km(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """两点球面距离（km）。p = (lat, lon)。"""
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def drive_km(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """估算车程距离（直线 × 绕路系数）。"""
    return haversine_km(p1, p2) * DRIVE_FACTOR


def fmt_km(km: float) -> str:
    if km < 1:
        return f"{max(50, int(km * 1000))} m"
    if km < 100:
        return f"{km:.1f} km"
    return f"{km:.0f} km"


def order_by_proximity(
    start: tuple[float, float] | None,
    items: list[dict],
) -> list[dict]:
    """从 start 出发的最近邻排序（有坐标的项参与排序，无坐标的保持原顺序排在末尾）。

    返回新列表，不修改入参；每项附带 distance_km（相对前一站的估算车程）。
    """
    with_loc: list[tuple[tuple[float, float], dict]] = []
    tail: list[dict] = []
    for it in items:
        p = loc_of(it)
        if p is None:
            tail.append(it)
        else:
            with_loc.append((p, it))

    ordered: list[dict] = []
    cur = start
    remaining = with_loc
    prev_point = start
    while remaining:
        if cur is not None:
            idx = min(range(len(remaining)), key=lambda i: haversine_km(cur, remaining[i][0]))
        else:
            idx = 0
        point, item = remaining.pop(idx)
        hop = drive_km(prev_point, point) if prev_point is not None else None
        entry = dict(item)
        entry["distance_km"] = round(hop, 1) if hop is not None else entry.get("distance_km")
        ordered.append(entry)
        prev_point, cur = point, point

    for it in tail:
        ordered.append(dict(it))
    return ordered


def pick_hotel_near_attractions(
    hotels: list[dict], attractions: list[dict]
) -> tuple[dict | None, dict[str, Any]]:
    """按「贴近景点群」选择酒店：返回 (最佳酒店, 统计信息)。

    评分：到各景点的平均车程（越近越好）+ 评分权重；有坐标的酒店优先于无坐标酒店。
    """
    locs = [loc_of(a) for a in attractions]
    points = [p for p in locs if p is not None]
    stats: dict[str, Any] = {"strategy": "unknown", "avg_km": None}

    best: dict | None = None
    best_key: tuple | None = None
    for h in hotels:
        hp = loc_of(h)
        if hp is None or not points:
            key = (1, 0.0, -h.get("rating", 0))  # 无坐标/无景点：退化为按评分
        else:
            avg = sum(drive_km(hp, p) for p in points) / len(points)
            key = (0, round(avg, 2), -h.get("rating", 0))
            if best_key is None or key < best_key:
                stats = {"strategy": "nearest", "avg_km": round(avg, 1)}
        if best_key is None or key < best_key:
            best, best_key = h, key

    if best is not None and best_key is not None and best_key[0] == 0:
        hp = loc_of(best)
        far = max((drive_km(hp, p) for p in points), default=0)
        stats["farthest_km"] = round(far, 1)
    return best, stats


def partition_days(
    attractions: list[dict], n_days: int, per_day: int = 2
) -> list[list[dict]]:
    """把一个城市的景点按地理就近原则切分到多天（最远优先聚类）。

    算法：每块从「距已分配景点最远」的景点作为种子（保证各天之间分散），
    再把种子附近的景点依次吸入同一天（保证同一天内部紧凑）——
    例如 丽江「玉龙雪山+蓝月谷」会被分到同一天，而不是与 40km 外的景点凑数。
    返回恰好 n_days 个块；同一景点绝不重复出现。
    """
    items = list(attractions)
    n_days = max(1, n_days)
    pts = [loc_of(a) for a in items]
    with_loc = [i for i, p in enumerate(pts) if p is not None]
    no_loc = [items[i] for i in range(len(items)) if pts[i] is None]

    blocks: list[list[int]] = []
    assigned: set[int] = set()
    pool = with_loc[:]
    while pool and len(blocks) < n_days:
        if not blocks:
            seed = pool[0]
        else:
            seed = max(pool, key=lambda j: min(haversine_km(pts[j], pts[k]) for k in assigned))
        block = [seed]
        assigned.add(seed)
        pool.remove(seed)
        while pool and len(block) < per_day:
            nxt = min(pool, key=lambda k: min(haversine_km(pts[k], pts[m]) for m in block))
            block.append(nxt)
            assigned.add(nxt)
            pool.remove(nxt)
        blocks.append([items[i] for i in block])

    # 无坐标的景点排进剩余空块；仍有剩余则并入最后一块（保持可见，不丢弃）
    while no_loc and len(blocks) < n_days:
        blocks.append([no_loc.pop(0)])
    if no_loc and blocks:
        blocks[-1].extend(no_loc)
    while len(blocks) < n_days:
        blocks.append([])
    return blocks[:n_days]


def city_route_summary(day_attrs: list[dict], hotel: dict | None) -> str:
    """生成当日动线描述：酒店 → A → B（车程约 X km）。"""
    if not day_attrs:
        return ""
    names = [a.get("name", "") for a in day_attrs]
    hops = [a.get("distance_km") for a in day_attrs if isinstance(a.get("distance_km"), (int, float))]
    total = sum(hops)
    start = hotel.get("name", "酒店") if hotel else "酒店"
    arrow = " → ".join([start] + names)
    if total > 0:
        return f"{arrow}（市内车程约 {fmt_km(total)}）"
    return arrow


def dedupe_by_name(items: Iterable[dict]) -> list[dict]:
    """按名称去重（保持首次出现顺序）。"""
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        name = it.get("name", "")
        if name and name not in seen:
            seen.add(name)
            out.append(it)
    return out
