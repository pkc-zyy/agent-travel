"""系统状态 / RAG 检索演示 API。"""
from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.mcp_server.client import get_mcp_client
from app.rag.knowledge import get_knowledge_base
from app.services.catalog import known_cities
from app.services.llm import get_llm_client

router = APIRouter(tags=["system"])

_AGENT_ROSTER = [
    {"name": "主管协调器", "emoji": "🧠", "role": "意图识别、任务分发、结果整合"},
    {"name": "行程规划师", "emoji": "🧭", "role": "解析需求，设计行程框架"},
    {"name": "天气顾问", "emoji": "☀️", "role": "查询目的地天气与出行建议"},
    {"name": "酒店专家", "emoji": "🏨", "role": "按预算偏好推荐住宿"},
    {"name": "景点研究员", "emoji": "🏔️", "role": "挖掘目的地值得一去的景点"},
    {"name": "实时搜索员", "emoji": "🌐", "role": "网页搜索最新信息（门票/活动）"},
    {"name": "预算会计师", "emoji": "💰", "role": "核算行程人均成本"},
    {"name": "方案审查官", "emoji": "🕵️", "role": "审查方案质量，把关输出"},
    {"name": "反馈分析师", "emoji": "📝", "role": "收集反馈，沉淀改进经验"},
]


@router.get("/stats")
async def stats():
    settings = get_settings()
    kb = get_knowledge_base()
    kb_stats = kb.stats()
    try:
        tools = await get_mcp_client().list_tools()
    except Exception:
        tools = []
    from app.db.database import SessionLocal
    from sqlalchemy import func, select
    from app.db.models import Feedback, KnowledgeDoc, MemoryItem, Trip

    counts = {"trips": 0, "feedbacks": 0, "memories": 0, "knowledge_docs": 0}
    try:
        async with SessionLocal() as session:
            counts["trips"] = (await session.execute(select(func.count()).select_from(Trip))).scalar() or 0
            counts["feedbacks"] = (await session.execute(select(func.count()).select_from(Feedback))).scalar() or 0
            counts["memories"] = (await session.execute(select(func.count()).select_from(MemoryItem))).scalar() or 0
            counts["knowledge_docs"] = (await session.execute(select(func.count()).select_from(KnowledgeDoc))).scalar() or 0
    except Exception:
        pass

    return {
        "app": settings.app_name,
        "llm_mode": get_llm_client().mode,
        "rag": kb_stats,
        "mcp_tools": tools,
        "agents": _AGENT_ROSTER,
        "cities": known_cities(),
        "db_counts": counts,
    }


@router.get("/kb/search")
async def kb_search(q: str, k: int = 3):
    """RAG 混合检索演示（向量 + BM25 + RRF 融合）。"""
    kb = get_knowledge_base()
    docs = await kb.retrieve(q, k=k)
    return {
        "query": q,
        "backend": kb.vector_store.backend,
        "embedding_mode": kb.vector_store.provider.mode,
        "results": [
            {"id": d.id, "text": d.text, "meta": d.metadata, "score": round(d.score, 4)}
            for d in docs
        ],
    }


@router.get("/search")
async def web_search(q: str, k: int = 5):
    """网页搜索演示（Tavily/SerpAPI/DuckDuckGo/Bing 多 provider 降级）。"""
    from app.services.web_search import get_web_search_service

    results = await get_web_search_service().search(q, k)
    return {"query": q, "results": results, "count": len(results)}
