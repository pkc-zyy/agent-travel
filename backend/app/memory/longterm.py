"""长期记忆：从对话与反馈中沉淀用户偏好/事实/教训。

存储双通道：
  1. SQLite（memory_items）：结构化、可管理（增删查）；
  2. 向量库（user_memory 集合）：支持语义召回。

记忆管理策略：
  - 去重（content 唯一约束），重复出现强化 hit_count（间隔遗忘曲线简化版）；
  - 检索时按 score=0.6*语义相似度 + 0.4*命中强度 排序。
"""
from __future__ import annotations

import asyncio
import re
from functools import lru_cache
from typing import Any

from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.db.models import MemoryItem
from app.prompts import MEMORY_EXTRACT_SYSTEM
from app.rag.hybrid import HybridRetriever
from app.rag.vector_store import VectorStore
from app.rag.bm25 import BM25Index

_PREF_PATTERNS = [
    (re.compile(r"(?:我)?(?:喜欢|偏爱|偏好|更爱|热爱)([^。，；,.!！?？]{2,20})"), "preference"),
    (re.compile(r"(?:我)?(?:不喜欢|不爱|讨厌|怕|忌)([^。，；,.!！?？]{2,20})"), "preference"),
    (re.compile(r"(?:预算|人均|花费|花销)[是约在]?([^。，；,.!！?？]{2,20})"), "fact"),
    (re.compile(r"(?:从|在)([^。，；,.!！?？]{2,10}?)(?:出发|开始)"), "fact"),
    (re.compile(r"(?:带|和|陪)([^。，；,.!！?？]{2,10}?)(?:一起|同行|去)"), "fact"),
    (re.compile(r"(?:去|到|想?去|目的地)([^。，；,.!！?？]{2,12}?)(?:玩|旅行|旅游|度假)"), "fact"),
]


class LongTermMemory:
    def __init__(self):
        self._vector = VectorStore("user_memory", None)
        self._bm25 = BM25Index()
        self._retriever = HybridRetriever(self._vector, self._bm25, vector_top_k=8, bm25_top_k=8)
        from app.config import get_settings

        self._sig_path = get_settings().vector_dir / "user_memory.sig"

    # ---------- 嵌入源签名（与知识库一致，切换后自动重建） ----------
    @staticmethod
    def _sig_key(sig: tuple[str, str]) -> str:
        return f"{sig[0]}:{sig[1]}"

    def _stored_signature(self) -> str:
        try:
            if self._sig_path.exists():
                return self._sig_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return ""

    def _save_signature(self, sig: tuple[str, str]) -> None:
        try:
            self._sig_path.write_text(self._sig_key(sig), encoding="utf-8")
        except Exception:
            pass

    async def _rebuild_from_db(self, provider) -> None:
        """清空向量索引，从 SQLite 重新导入全部记忆。"""
        await asyncio.to_thread(self._vector.clear)
        await asyncio.to_thread(self._bm25.clear)
        async with SessionLocal() as session:
            rows = (await session.execute(select(MemoryItem))).scalars().all()
            for item in rows:
                await asyncio.to_thread(
                    self._vector.add,
                    [f"mem-{item.id}"],
                    [item.content],
                    [{"user_id": item.user_id, "kind": item.kind, "memory_id": item.id}],
                )
                await asyncio.to_thread(
                    self._bm25.add,
                    [f"mem-{item.id}"],
                    [item.content],
                    [{"user_id": item.user_id, "kind": item.kind, "memory_id": item.id}],
                )

    async def ensure_index(self) -> None:
        """嵌入源配置变化时重建记忆向量索引（从 DB 重导入）。"""
        provider = self._vector.provider
        configured = provider.configured_signature()
        if self._stored_signature() == self._sig_key(configured):
            return
        # 激活实际可用的嵌入模式
        if configured[0] == "api" and provider.probe_api():
            provider.activate("api")
        else:
            provider.activate("local")
        await self._rebuild_from_db(provider)
        self._save_signature(configured)

    # ---------- 写入 ----------
    async def add(self, user_id: str, kind: str, content: str, source: str = "chat") -> MemoryItem | None:
        await self.ensure_index()
        content = content.strip()
        if len(content) < 2:
            return None
        async with SessionLocal() as session:
            existing = (
                await session.execute(
                    select(MemoryItem).where(
                        MemoryItem.user_id == user_id, MemoryItem.content == content
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.hit_count += 1
                existing.score = min(2.0, existing.score + 0.2)
                await session.commit()
                await session.refresh(existing)
                # 向量库同步（无需重复写入）
                return existing

            item = MemoryItem(user_id=user_id, kind=kind, content=content, source=source)
            session.add(item)
            await session.commit()
            await session.refresh(item)

        # 写入向量库（后台执行，避免阻塞）
        await asyncio.to_thread(
            self._vector.add, [f"mem-{item.id}"], [content], [{"user_id": user_id, "kind": kind, "memory_id": item.id}]
        )
        await asyncio.to_thread(
            self._bm25.add, [f"mem-{item.id}"], [content], [{"user_id": user_id, "kind": kind, "memory_id": item.id}]
        )
        return item

    # ---------- 读取 ----------
    async def list_items(self, user_id: str, kind: str | None = None) -> list[MemoryItem]:
        async with SessionLocal() as session:
            stmt = select(MemoryItem).where(MemoryItem.user_id == user_id)
            if kind:
                stmt = stmt.where(MemoryItem.kind == kind)
            stmt = stmt.order_by(MemoryItem.updated_at.desc()).limit(200)
            rows = (await session.execute(stmt)).scalars().all()
            return list(rows)

    async def delete(self, memory_ids: list[int]) -> int:
        async with SessionLocal() as session:
            result = await session.execute(
                delete(MemoryItem).where(MemoryItem.id.in_(memory_ids))
            )
            await session.commit()
            return result.rowcount or 0

    # ---------- 检索 ----------
    async def retrieve(self, user_id: str, query: str, k: int | None = None) -> list[dict]:
        """混合召回用户长期记忆，融合 语义相似度 与 记忆强度。"""
        from app.config import get_settings

        await self.ensure_index()
        k = k or get_settings().memory_top_k
        where = {"user_id": user_id}
        hits = await self._retriever.retrieve(query, k=k * 2, where=where)

        # 从 DB 取结构化信息
        mem_ids = [h.metadata.get("memory_id") for h in hits if h.metadata.get("memory_id")]
        items_by_id: dict[int, MemoryItem] = {}
        if mem_ids:
            async with SessionLocal() as session:
                rows = (
                    await session.execute(select(MemoryItem).where(MemoryItem.id.in_(mem_ids)))
                ).scalars().all()
                items_by_id = {r.id: r for r in rows}

        results: list[dict] = []
        for h in hits:
            item = items_by_id.get(h.metadata.get("memory_id"))
            if item is None:
                continue
            strength = 0.6 + min(0.4, item.hit_count * 0.1)  # 命中强化
            results.append(
                {
                    "id": item.id,
                    "kind": item.kind,
                    "content": item.content,
                    "source": item.source,
                    "semantic_score": round(float(h.score), 4),
                    "strength": round(strength, 2),
                    "hit_count": item.hit_count,
                }
            )
        results.sort(key=lambda r: r["semantic_score"] * r["strength"], reverse=True)
        return results[:k]

    # ---------- 抽取 ----------
    async def extract_and_store(self, user_id: str, text: str, source: str = "chat") -> list[MemoryItem]:
        """从用户文本中抽取偏好/事实并写入长期记忆（LLM 优先，规则兜底）。"""
        stored: list[MemoryItem] = []
        candidates: list[tuple[str, str]] = []

        # 规则抽取
        for pat, kind in _PREF_PATTERNS:
            for m in pat.finditer(text):
                phrase = m.group(1).strip().rstrip("的，")
                if len(phrase) >= 2 and len(phrase) <= 24:
                    candidates.append((kind, f"{'喜欢' if kind=='preference' else ''}{phrase}"))

        # 关键词偏好（亲子/情侣/穷游/豪华等）
        keyword_prefs = {
            "亲子": "偏好亲子友好行程", "带孩子": "偏好亲子友好行程", "带娃": "偏好亲子友好行程",
            "情侣": "偏好浪漫情侣行程", "蜜月": "偏好浪漫情侣行程", "度蜜月": "偏好浪漫情侣行程",
            "穷游": "偏好经济型消费", "性价比": "偏好经济型消费", "省钱": "偏好经济型消费",
            "豪华": "偏好高端豪华体验", "高端": "偏好高端豪华体验", "奢华": "偏好高端豪华体验",
            "美食": "偏好美食体验", "吃货": "偏好美食体验",
            "自然风光": "偏好自然风光", "看海": "偏好海滨海岛", "海边": "偏好海滨海岛",
            "古镇": "偏好古镇文化", "文艺": "偏好文艺氛围", "摄影": "偏好摄影打卡",
            "徒步": "偏好徒步登山", "登山": "偏好徒步登山", "潜水": "偏好水上运动",
            "慢": "偏好慢节奏休闲", "休闲": "偏好慢节奏休闲", "不赶": "偏好慢节奏休闲",
            "老人": "需要照顾同行老人", "爸妈": "需要照顾同行老人",
        }
        for kw, pref in keyword_prefs.items():
            if kw in text:
                candidates.append(("preference", pref))

        seen: set[str] = set()
        for kind, content in candidates:
            if content in seen:
                continue
            seen.add(content)
            item = await self.add(user_id, kind, content, source)
            if item:
                stored.append(item)

        if not stored:
            # LLM 抽取（可选，增强）
            from app.services.llm import get_llm_client

            llm = get_llm_client()
            if llm.mode == "llm":
                try:
                    parsed = await llm.chat_json(
                        [
                            {"role": "system", "content": MEMORY_EXTRACT_SYSTEM},
                            {"role": "user", "content": text[:800]},
                        ]
                    )
                    for it in (parsed or []):
                        if isinstance(it, dict) and it.get("content"):
                            item = await self.add(user_id, it.get("kind", "preference"), it["content"], source)
                            if item:
                                stored.append(item)
                except Exception:
                    pass
        return stored


@lru_cache
def get_long_term_memory() -> LongTermMemory:
    return LongTermMemory()
