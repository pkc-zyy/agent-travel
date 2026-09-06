"""反馈分析师 Agent：处理用户反馈 → 提取教训 → 写入长期记忆 → 反馈闭环学习。"""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.prompts import FEEDBACK_LESSONS_SYSTEM

_TAG_LESSONS = {
    "酒店太贵": "为 {user} 优先推荐经济实惠的住宿",
    "住宿": "改进住宿筛选，优先符合 {user} 预算档位",
    "路线太赶": "为 {user} 放慢行程节奏，每天不超过 3 个核心景点",
    "太累": "为 {user} 安排更宽松的行程节奏",
    "景点一般": "为 {user} 精选更高评分、更契合兴趣的景点",
    "天气": "为 {user} 更早提醒天气变化并预留室内备选方案",
    "交通": "为 {user} 优化城际交通衔接，减少中转等待",
    "美食": "为 {user} 增加本地特色美食推荐",
    "排队": "为 {user} 提前预约热门景点并错峰游览",
    "价格": "为 {user} 提供更透明的预算明细与省钱建议",
}


class FeedbackAgent(BaseAgent):
    name = "反馈分析师"
    emoji = "📝"
    role = "收集用户反馈，沉淀偏好与改进经验"

    async def process(self, user_id: str, rating: int, comment: str,
                      tags: list[str]) -> dict[str, Any]:
        await self.emit("running", "正在分析反馈并更新长期记忆…")

        lessons: list[str] = []
        text = comment + " " + " ".join(tags)

        # 1) 标签 → 教训
        for tag, lesson in _TAG_LESSONS.items():
            if tag in text:
                lessons.append(lesson.format(user=user_id))

        # 2) 低分评论 → LLM 抽取（可选）
        if rating <= 3 and not lessons:
            from app.services.llm import get_llm_client

            llm = get_llm_client()
            if llm.mode == "llm":
                try:
                    parsed = await llm.chat_json(
                        [
                            {"role": "system", "content": FEEDBACK_LESSONS_SYSTEM},
                            {"role": "user", "content": f"评分{rating}/5：{comment}"},
                        ]
                    )
                    if isinstance(parsed, list):
                        lessons.extend(str(x) for x in parsed[:3])
                except Exception:
                    pass

        if not lessons:
            lessons.append(
                f"用户评分 {rating}/5：继续优化旅行体验"
                if rating >= 4
                else f"用户评分 {rating}/5，需针对性改进"
            )

        # 3) 写入长期记忆（kind=lesson）
        from app.memory.longterm import get_long_term_memory

        ltm = get_long_term_memory()
        stored: list[dict] = []
        for lesson in lessons:
            item = await ltm.add(user_id, "lesson", lesson, "feedback")
            if item:
                stored.append(item.to_dict())

        # 4) 将评论本身作为偏好记忆补充
        if comment.strip():
            await ltm.add(user_id, "fact", f"用户反馈：{comment.strip()[:120]}", "feedback")

        await self.emit("done", f"反馈已归档，学习到 {len(stored)} 条改进经验")
        return {"lessons": lessons, "stored": len(stored)}

    async def acknowledge(self, rating: int, lessons: list[str]) -> str:
        if rating >= 4:
            head = "感谢您的认可！我们会把这份好评转化为持续的动力 ✨"
        else:
            head = "感谢您的反馈！您的意见对我们非常重要 🙏"
        lines = [head, ""]
        if lessons:
            lines.append("我们已经把以下经验写入长期记忆，下次规划时会自动应用：")
            lines.append("")
            for lesson in lessons[:3]:
                lines.append(f"- ✅ {lesson}")
        else:
            lines.append("我们已记录您的反馈。")
        return "\n".join(lines)
