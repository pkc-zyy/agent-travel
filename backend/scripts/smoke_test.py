"""端到端冒烟测试：知识库 → MCP → 多 Agent 规划 → 反馈学习 → 记忆。

运行：python -m scripts.smoke_test
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: F401  确保包可导入


async def main() -> None:
    from app.db.database import init_db
    from app.rag.knowledge import get_knowledge_base

    print("=" * 64)
    print("1) 初始化数据库与 RAG 索引")
    print("=" * 64)
    await init_db()
    kb = get_knowledge_base()
    stat = await kb.build(force=True)
    print("  RAG:", stat, kb.stats())

    print("\n" + "=" * 64)
    print("2) RAG 混合检索（向量 + BM25 + RRF）")
    print("=" * 64)
    for q in ["丽江适合情侣的酒店", "北京亲子必去景点", "三亚 海滩 潜水"]:
        docs = await kb.retrieve(q, k=3)
        print(f"  查询「{q}」→")
        for d in docs:
            print(f"    - [{d.metadata.get('kind')}] {d.text[:60]}… (score={d.score:.4f})")

    print("\n" + "=" * 64)
    print("3) MCP 客户端连接与工具调用")
    print("=" * 64)
    from app.mcp_server.client import get_mcp_client

    mcp = get_mcp_client()
    tools = await mcp.list_tools()
    print("  MCP 工具:", tools)
    weather = await mcp.call_tool("get_weather", {"city": "北京"})
    print("  天气(北京):", weather.get("condition"), weather.get("t_min"), "~", weather.get("t_max"), "℃", f"[{weather.get('source')}]")
    hotels = await mcp.call_tool("search_hotels", {"city": "丽江", "budget": "舒适", "keywords": "情侣"})
    print("  酒店(丽江/舒适/情侣):", [h["name"] for h in hotels])

    print("\n" + "=" * 64)
    print("4) 主管协调器 → 多 Agent 并发规划")
    print("=" * 64)
    from app.agents.orchestrator import get_orchestrator

    orchestrator = get_orchestrator()
    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)
        if ev.get("type") == "agent":
            print(f"    [{ev.get('emoji')} {ev.get('name')}] {ev.get('status')}: {ev.get('message')}")

    result = await orchestrator.handle(
        "帮我规划云南昆明-大理-丽江 5 日游，人均4000-5000元，喜欢自然风光和美食",
        session_id="smoke-session",
        user_id="smoke-user",
        emit=emit,
    )
    print(f"\n  意图: {result['intent']}")
    plan = (result.get("data") or {}).get("plan", {})
    print(f"  标题: {plan.get('title')}")
    print(f"  城市: {plan.get('cities')}  天数: {plan.get('days')}")
    print(f"  预算: {plan.get('budget', {}).get('total_per_person')} 元/人")
    print(f"  每日: {[(d['day'], d['city'], len(d['attractions'])) for d in plan.get('schedule', [])]}")
    print(f"  审查: {plan.get('review')}")
    print(f"  回复长度: {len(result['reply'])} 字符")

    print("\n" + "=" * 64)
    print("5) 单意图：天气 / 酒店 / 景点")
    print("=" * 64)
    for msg in ["北京明天天气怎么样", "推荐三亚适合亲子的酒店", "成都必去的景点"]:
        r = await orchestrator.handle(msg, session_id="smoke-session", user_id="smoke-user", emit=emit)
        print(f"  「{msg}」→ intent={r['intent']}")

    print("\n" + "=" * 64)
    print("6) 反馈闭环：反馈 → 学习 → 长期记忆")
    print("=" * 64)
    from app.agents.base import AgentContext
    from app.agents.feedback_agent import FeedbackAgent
    from app.config import get_settings
    from app.memory.longterm import get_long_term_memory

    ctx = AgentContext(user_id="smoke-user", mcp=mcp, settings=get_settings())
    agent = FeedbackAgent(ctx)
    result = await agent.process("smoke-user", 2, "上次行程太赶了，酒店太贵", ["路线太赶", "酒店太贵"])
    print("  学习到的经验:", result["lessons"])
    mems = await get_long_term_memory().retrieve("smoke-user", "推荐经济实惠的住宿", k=3)
    print("  检索相关记忆:")
    for m in mems:
        print(f"    - [{m['kind']}] {m['content']} (strength={m['strength']})")

    print("\n" + "=" * 64)
    print("7) 记忆抽取：从对话中沉淀偏好")
    print("=" * 64)
    stored = await get_long_term_memory().extract_and_store(
        "smoke-user", "我喜欢看海，预算人均3000，带两个孩子，喜欢美食"
    )
    for s in stored:
        print(f"    + [{s.kind}] {s.content}")

    print("\n✅ 冒烟测试全部通过")
    await mcp.aclose()


if __name__ == "__main__":
    asyncio.run(main())
