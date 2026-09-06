"""最终集成验证：模拟前端完整用户旅程（经由 Vite 代理，与浏览器路径一致）。"""
import asyncio
import json
import sys

import httpx

BASE = "http://127.0.0.1:5173/api"


async def main():
    async with httpx.AsyncClient(timeout=120) as c:
        print("=" * 60)
        print("① 智能规划：流式对话 → 生成方案")
        print("=" * 60)
        events = []
        payload = {"message": "帮我规划成都-重庆 4 日游，喜欢美食，预算人均3000", "session_id": "journey", "user_id": "journey-user", "stream": True}
        async with c.stream("POST", f"{BASE}/chat/stream", json=payload) as r:
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        result = next((e for e in events if e["type"] == "result"), None)
        agents = [e for e in events if e["type"] == "agent"]
        assert result, "缺少 result 事件"
        plan = result["data"]["plan"]
        print(f"  ✓ 事件 {len(events)} 个（{len(agents)} 个 Agent 协作事件）")
        print(f"  ✓ 方案：{plan['title']}，{plan['days']} 天，人均 ¥{plan['budget']['total_per_person']}")
        day_summary = ", ".join(f"D{d['day']} {d['city']}({len(d['attractions'])}景)" for d in plan["schedule"])
        print(f"  ✓ 每日安排：{day_summary}")
        trip_id = result["data"]["trip_id"]
        print(f"  ✓ 行程已保存 trip_id={trip_id}")

        print("\n" + "=" * 60)
        print("② 行程列表 → 详情")
        print("=" * 60)
        plans = (await c.get(f"{BASE}/plans", params={"user_id": "journey-user"})).json()
        print(f"  ✓ 行程数：{len(plans)}")
        detail = (await c.get(f"{BASE}/plans/{trip_id}")).json()
        print(f"  ✓ 详情标题：{detail['title']}，含 markdown {len(detail.get('markdown', ''))} 字符")

        print("\n" + "=" * 60)
        print("③ 提交反馈 → 学习 → 长期记忆")
        print("=" * 60)
        fb = (await c.post(f"{BASE}/feedback", json={
            "user_id": "journey-user", "trip_id": trip_id,
            "rating": 2, "comment": "重庆那晚酒店太吵了，整体还不错",
            "tags": ["酒店太贵", "路线太赶"],
        })).json()
        print(f"  ✓ 反馈已提交 id={fb['feedback']['id']}，学习任务后台进行中")
        await asyncio.sleep(2.5)
        learned = (await c.get(f"{BASE}/feedback/learned", params={"user_id": "journey-user"})).json()
        print(f"  ✓ 学到经验 {len(learned)} 条：")
        for it in learned:
            print(f"    - {it['content']}")

        print("\n" + "=" * 60)
        print("④ 长期记忆管理")
        print("=" * 60)
        mems = (await c.get(f"{BASE}/memory", params={"user_id": "journey-user"})).json()
        print(f"  ✓ 长期记忆 {len(mems)} 条：")
        for it in mems[:4]:
            print(f"    - [{it['kind']}] {it['content']}")

        print("\n" + "=" * 60)
        print("⑤ 记忆影响下一次规划（反馈后的改进）")
        print("=" * 60)
        payload2 = {"message": "再帮我规划一次重庆2日游", "session_id": "journey", "user_id": "journey-user", "stream": False}
        r2 = (await c.post(f"{BASE}/chat", json=payload2)).json()
        print(f"  ✓ 意图={r2['intent']}，回复 {len(r2['reply'])} 字符")

        print("\n" + "=" * 60)
        print("⑥ 系统状态")
        print("=" * 60)
        stats = (await c.get(f"{BASE}/stats")).json()
        print(f"  ✓ llm={stats['llm_mode']} rag={stats['rag']['docs']}篇({stats['rag']['vector_backend']}) mcp_tools={len(stats['mcp_tools'])} db={stats['db_counts']}")

        print("\n✅ 全链路验证通过")


if __name__ == "__main__":
    asyncio.run(main())
