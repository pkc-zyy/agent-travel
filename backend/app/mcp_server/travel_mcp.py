"""TravelAgent MCP Server：向任何 MCP 客户端（Claude Desktop / Cursor / 自研 Agent）暴露旅行工具。

- 工具：天气 / 酒店 / 景点 / 城市指南 / RAG 知识检索 / 反馈沉淀 / 用户偏好
- 传输：进程内（memory）+ SSE（HTTP /mcp）+ stdio（python -m app.mcp_server.travel_mcp）

启动方式：
  - 进程内：由 FastAPI 应用启动时挂载（见 app/main.py）
  - 独立 stdio：`python -m app.mcp_server.travel_mcp`
"""
from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.prompts import MCP_INSTRUCTIONS
from app.rag.knowledge import get_knowledge_base
from app.services.catalog import (
    get_attraction_service,
    get_city_info,
    get_hotel_service,
    known_cities,
)
from app.services.runtime_config import is_llm_ready
from app.services.weather import get_weather_service

mcp = FastMCP(
    "travel-agent",
    instructions=MCP_INSTRUCTIONS,
)


def _prefer_amap(amap_ready: bool) -> bool:
    """数据源优先级策略：接入大模型后，高德实时数据优先于本地知识库；
    离线模式（未配置 LLM）保持本地精选数据优先，保证演示质量。"""
    return amap_ready and is_llm_ready()


# ==================== 天气 ====================
@mcp.tool(description="查询指定城市未来天气，可选日期（YYYY-MM-DD）")
async def get_weather(city: str, date: str | None = None) -> dict:
    """查询天气（通过 MCP 调用）。本地无坐标且配置了高德 Key 时自动地理编码。"""
    info = get_city_info(city)
    lat, lon = info.get("lat"), info.get("lon")
    if lat is None or lon is None:
        from app.services.amap import get_amap_service

        amap = get_amap_service()
        if amap.is_ready():
            loc = await amap.geocode(city)
            if loc:
                lat, lon = loc["lat"], loc["lon"]
    return await get_weather_service().get_weather(city, lat, lon, date)


# ==================== 酒店 ====================
@mcp.tool(description="按城市/预算（经济/舒适/豪华）/关键词推荐酒店（优先高德地图真实 POI，回退本地知识库）")
async def search_hotels(
    city: str = "",
    budget: str = "",
    keywords: str = "",
    top_k: int = 3,
) -> list[dict]:
    """搜索酒店。"""
    from app.services.amap import get_amap_service

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]

    # 1) 高德地图真实酒店 POI（配置了 Key 时启用）
    try:
        amap = get_amap_service()
        if amap.is_ready():
            amap_result = await amap.search_hotels(city=city, budget=budget, keywords=kw_list, top_k=top_k)
            if amap_result:
                return amap_result
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).warning("高德酒店检索失败，回退本地数据: %s", e)

    # 2) 本地知识库
    local = get_hotel_service().search(
        city=city or None,
        budget=budget or None,
        keywords=kw_list,
        top_k=top_k,
    )
    if local:
        return local

    # 3) LLM 生成兜底（长尾城市，结果标注「AI 参考」）
    from app.services.llm_knowledge import llm_hotels

    llm_result = await llm_hotels(city=city, budget=budget, keywords=kw_list, n=top_k)
    return llm_result or []


# ==================== 景点 ====================
@mcp.tool(description="按城市/兴趣关键词推荐景点（接入 LLM 后高德实时 POI 优先，其次本地知识库，最后 LLM 生成）")
async def search_attractions(city: str = "", interests: str = "", top_k: int = 5) -> list[dict]:
    """搜索景点。数据源优先级：LLM 已接入时 高德 > 本地 > LLM生成；离线时 本地 > 高德 > LLM生成。"""
    from app.services.amap import get_amap_service

    interest_list = [i.strip() for i in interests.split(",") if i.strip()]
    amap = get_amap_service()
    amap_ready = amap.is_ready()
    prefer_amap = _prefer_amap(amap_ready)
    local = get_attraction_service().search(
        city=city or None,
        interests=interest_list,
        top_k=top_k,
    )

    # 1) 高德实时 POI（LLM 已接入时优先；否则仅作本地缺数据时的兜底）
    if prefer_amap or (amap_ready and not local):
        try:
            amap_result = await amap.search_attractions(city=city, interests=interest_list, top_k=top_k)
            if amap_result:
                return amap_result
        except Exception as e:  # noqa: BLE001
            logging.getLogger(__name__).warning("高德景点检索失败: %s", e)

    # 2) 本地知识库（精选 25 城，含坐标/门票/时长）
    if local:
        return local

    # 3) LLM 生成兜底（长尾城市，结果标注「AI 参考」；多请求几个以覆盖多日行程）
    from app.services.llm_knowledge import llm_attractions

    llm_result = await llm_attractions(city=city, interests=interest_list, n=max(8, top_k))
    return llm_result[:max(top_k, 8)] if llm_result else []


# ==================== 城市信息 ====================
@mcp.tool(description="获取城市基础信息（简介/特色/美食/最佳季节）")
def get_city_info_tool(city: str) -> dict:
    """城市信息。"""
    return get_city_info(city)


@mcp.tool(description="列出系统支持的旅行城市")
def list_cities() -> list[str]:
    return known_cities()


# ==================== RAG 知识检索 ====================
@mcp.tool(description="对旅行知识库（城市指南/景点/酒店/贴士）执行 RAG 混合检索")
async def kb_search(query: str, k: int = 3) -> list[dict]:
    """RAG 混合检索（向量 + BM25 + RRF 融合）。"""
    kb = get_knowledge_base()
    docs = await kb.retrieve(query, k=k)
    return [
        {"id": d.id, "text": d.text[:300], "meta": d.metadata, "score": round(d.score, 4)}
        for d in docs
    ]


@mcp.tool(description="获取指定城市的旅行指南全文")
async def get_city_guide(city: str) -> str:
    """城市指南。"""
    kb = get_knowledge_base()
    docs = await kb.retrieve(city, k=3, kind="guide")
    guide = next((d.text for d in docs if d.metadata.get("city") == city), None)
    if guide:
        return guide
    return f"暂无 {city} 的指南，可检索: {', '.join(known_cities())}"


# ==================== 网页搜索 ====================
@mcp.tool(description="实时网页搜索：查询门票/开放时间/最新活动等互联网信息")
async def web_search(query: str, top_k: int = 5) -> list[dict]:
    """网页搜索（Tavily/SerpAPI/DuckDuckGo/Bing 多 provider 降级）。"""
    from app.services.web_search import get_web_search_service

    return await get_web_search_service().search(query, top_k)


# ==================== 反馈 / 记忆 ====================
@mcp.tool(description="沉淀用户反馈：评分(1-5)、评论、标签，供系统学习改进")
async def save_feedback(
    user_id: str = "default",
    trip_id: int | None = None,
    rating: int = 5,
    comment: str = "",
    tags: str = "",
) -> dict:
    """保存反馈（同步写库）。"""
    from app.db.database import SessionLocal
    from app.db.models import Feedback

    async with SessionLocal() as session:
        fb = Feedback(
            user_id=user_id,
            trip_id=trip_id,
            rating=max(1, min(5, rating)),
            comment=comment,
            tags=tags,
        )
        session.add(fb)
        await session.commit()
        await session.refresh(fb)
        return fb.to_dict()


@mcp.tool(description="读取用户的长期记忆偏好")
async def get_user_preferences(user_id: str = "default") -> list[dict]:
    """用户偏好记忆。"""
    from app.memory.longterm import get_long_term_memory

    items = await get_long_term_memory().list_items(user_id)
    return [it.to_dict() for it in items]


if __name__ == "__main__":
    # 独立 stdio 模式：供外部 MCP 客户端连接
    mcp.run()
