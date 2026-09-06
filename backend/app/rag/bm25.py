"""BM25 稀疏检索（rank-bm25，Okapi 变体），用于 RAG 混合召回中的关键词通道。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.rag.embeddings import tokenize
from app.rag.vector_store import RetrievedDoc


@dataclass
class BM25Entry:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._entries: list[BM25Entry] = []
        self._corpus: list[list[str]] = []
        self._bm25 = None
        self._id_map: dict[str, BM25Entry] = {}

    def add(self, ids: list[str], texts: list[str], metadatas: list[dict] | None = None):
        for i, doc_id in enumerate(ids):
            entry = BM25Entry(
                id=doc_id,
                text=texts[i],
                metadata=(metadatas or [{}] * len(ids))[i],
            )
            self._id_map[doc_id] = entry
            self._entries.append(entry)
            self._corpus.append(tokenize(texts[i]))
        self._rebuild()

    def _rebuild(self):
        if not self._corpus:
            self._bm25 = None
            return
        from rank_bm25 import BM25Okapi

        self._bm25 = BM25Okapi(self._corpus, k1=self.k1, b=self.b)

    def search(self, query: str, k: int = 5, where: dict | None = None) -> list[RetrievedDoc]:
        if self._bm25 is None or not query.strip():
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        scores = self._bm25.get_scores(q_tokens)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out: list[RetrievedDoc] = []
        for idx in order:
            entry = self._entries[idx]
            if where and not all(entry.metadata.get(kk) == vv for kk, vv in where.items()):
                continue
            out.append(
                RetrievedDoc(
                    id=entry.id,
                    text=entry.text,
                    metadata=dict(entry.metadata),
                    score=float(scores[idx]),
                )
            )
            if len(out) >= k:
                break
        return out

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        """清空全部条目（用于索引重建）。"""
        self._entries = []
        self._corpus = []
        self._id_map = {}
        self._bm25 = None

    def delete(self, ids: list[str]) -> int:
        """删除指定 id 的条目并重建索引，返回删除数量。"""
        target = set(ids)
        before = len(self._entries)
        keep = [(e, c) for e, c in zip(self._entries, self._corpus) if e.id not in target]
        self._entries = [e for e, _ in keep]
        self._corpus = [c for _, c in keep]
        for i in target:
            self._id_map.pop(i, None)
        self._rebuild()
        return before - len(self._entries)
