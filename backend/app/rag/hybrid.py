"""混合召回：向量通道（语义） + BM25 通道（关键词） → RRF 融合 → 结果。

设计要点：
- 查询扩展：识别城市/主题关键词生成多路查询，提升召回。
- RRF 融合：reciprocal rank fusion，稳定融合异构排序，不依赖分数尺度。
- 过滤：支持按元数据（如 city / kind）过滤。
"""
from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.rag.bm25 import BM25Index
from app.rag.vector_store import RetrievedDoc, VectorStore

_CITY_RE = re.compile(
    r"(北京|上海|广州|深圳|成都|重庆|杭州|西安|昆明|大理|丽江|三亚|厦门|青岛|苏州|南京|武汉|长沙)"
)


def expand_query(query: str) -> list[str]:
    """查询扩展：原查询 + 命中城市组合查询。"""
    queries = [query.strip()]
    cities = _CITY_RE.findall(query)
    if cities:
        # 去除重复且保持顺序
        seen: list[str] = []
        for c in cities:
            if c not in seen:
                seen.append(c)
        joined = " ".join(seen)
        queries.append(f"{joined} 旅行 攻略")
        queries.append(f"{joined} 景点 酒店")
    return [q for q in queries if q]


class HybridRetriever:
    def __init__(
        self,
        vector_store: VectorStore,
        bm25: BM25Index,
        vector_top_k: int | None = None,
        bm25_top_k: int | None = None,
    ):
        self.vector_store = vector_store
        self.bm25 = bm25
        s = get_settings()
        self.vector_top_k = vector_top_k or s.vector_top_k
        self.bm25_top_k = bm25_top_k or s.bm25_top_k
        self.final_k = s.rag_final_k

    @staticmethod
    def _rrf_fuse(ranked: list[list[RetrievedDoc]], k: int = 60) -> list[RetrievedDoc]:
        """Reciprocal Rank Fusion。"""
        fused: dict[str, tuple[float, RetrievedDoc]] = {}
        for rank_list in ranked:
            for rank, doc in enumerate(rank_list):
                score = 1.0 / (k + rank + 1)
                if doc.id in fused:
                    prev_score, prev_doc = fused[doc.id]
                    fused[doc.id] = (prev_score + score, prev_doc)
                else:
                    fused[doc.id] = (score, doc)
        ordered = sorted(fused.values(), key=lambda x: x[0], reverse=True)
        return [doc for _, doc in ordered]

    async def retrieve(
        self, query: str, k: int | None = None, where: dict[str, Any] | None = None
    ) -> list[RetrievedDoc]:
        final_k = k or self.final_k
        queries = expand_query(query)

        vector_hits: list[RetrievedDoc] = []
        bm25_hits: list[RetrievedDoc] = []
        for q in queries:
            vector_hits.extend(self.vector_store.query(q, k=self.vector_top_k, where=where))
            bm25_hits.extend(self.bm25.search(q, k=self.bm25_top_k, where=where))

        # 通道内去重（保序）
        def dedup(docs: list[RetrievedDoc]) -> list[RetrievedDoc]:
            seen: set[str] = set()
            out: list[RetrievedDoc] = []
            for d in docs:
                if d.id not in seen:
                    seen.add(d.id)
                    out.append(d)
            return out

        fused = self._rrf_fuse([dedup(vector_hits), dedup(bm25_hits)])

        # 城市感知重排：查询命中某城市时，提升该城市文档的排序（元数据 boost）
        city_hits = _CITY_RE.findall(query)
        if city_hits:
            boost = 1.6
            for doc in fused:
                doc_city = doc.metadata.get("city") or ""
                if any(c == doc_city for c in city_hits):
                    doc.score = float(doc.score) * boost
            fused.sort(key=lambda d: d.score, reverse=True)

        return fused[:final_k]
