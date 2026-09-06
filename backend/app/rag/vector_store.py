"""向量数据库：默认 ChromaDB（持久化），导入失败时自动降级为内置 NumPy 向量库。
两者实现一致的 add / query 接口，上层无感切换。"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.config import get_settings
from app.rag.embeddings import get_embedding_provider, tokenize

try:
    import chromadb

    _HAS_CHROMA = True
except Exception:  # pragma: no cover
    _HAS_CHROMA = False


@dataclass
class RetrievedDoc:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class _NumpyVectorStore:
    """轻量向量库：余弦相似度暴力检索（演示规模足够），npz + json 持久化。"""

    def __init__(self, path: str, dim: int):
        self.path = path
        self.dim = dim
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._metas: list[dict] = []
        self._matrix: np.ndarray | None = None
        self._load()

    def _load(self):
        if os.path.exists(self.path + ".npz") and os.path.exists(self.path + ".json"):
            try:
                data = np.load(self.path + ".npz", allow_pickle=False)
                self._matrix = data["matrix"]
                with open(self.path + ".json", encoding="utf-8") as f:
                    meta = json.load(f)
                self._ids = meta["ids"]
                self._texts = meta["texts"]
                self._metas = meta["metas"]
            except Exception:
                pass

    def _save(self):
        np.savez(self.path + ".npz", matrix=self._matrix)
        with open(self.path + ".json", "w", encoding="utf-8") as f:
            json.dump({"ids": self._ids, "texts": self._texts, "metas": self._metas}, f, ensure_ascii=False)

    def add(self, ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict] | None = None):
        new_rows = np.asarray(embeddings, dtype=np.float32)
        if self._matrix is None:
            self._matrix = new_rows
        else:
            self._matrix = np.vstack([self._matrix, new_rows])
        self._ids.extend(ids)
        self._texts.extend(texts)
        self._metas.extend(metadatas or [{}] * len(ids))
        self._save()

    def query(self, vector: list[float], k: int, where: dict | None = None) -> list[RetrievedDoc]:
        if self._matrix is None or self._matrix.shape[0] == 0:
            return []
        q = np.asarray(vector, dtype=np.float32)
        scores = self._matrix @ q  # 已归一化 → 余弦相似度
        order = np.argsort(-scores)
        out: list[RetrievedDoc] = []
        for idx in order:
            if where:
                meta = self._metas[int(idx)]
                if not all(meta.get(kk) == vv for kk, vv in where.items()):
                    continue
            out.append(
                RetrievedDoc(
                    id=self._ids[int(idx)],
                    text=self._texts[int(idx)],
                    metadata=dict(self._metas[int(idx)]),
                    score=float(scores[int(idx)]),
                )
            )
            if len(out) >= k:
                break
        return out

    def count(self) -> int:
        return len(self._ids)

    def delete(self, ids: set[str]) -> list[str]:
        """按 id 删除，返回被删除的 id。"""
        deleted = [i for i in self._ids if i in ids]
        if not deleted:
            return []
        keep = [i for i, id_ in enumerate(self._ids) if id_ not in ids]
        self._ids = [self._ids[i] for i in keep]
        self._texts = [self._texts[i] for i in keep]
        self._metas = [self._metas[i] for i in keep]
        if self._matrix is not None:
            self._matrix = self._matrix[keep] if keep else None
        self._save()
        return deleted


class VectorStore:
    """向量数据库统一门面。"""

    def __init__(self, name: str, vector_dir: str | None = None):
        self.name = name
        self.settings = get_settings()
        self.vector_dir = vector_dir or str(self.settings.vector_dir)
        self.provider = get_embedding_provider()
        os.makedirs(self.vector_dir, exist_ok=True)
        self._chroma = None
        self._client = None
        self._numpy: _NumpyVectorStore | None = None
        self._backend = self._init_backend()

    def _init_backend(self):
        if _HAS_CHROMA:
            try:
                client = chromadb.PersistentClient(path=self.vector_dir)
                self._client = client
                self._chroma = client.get_or_create_collection(
                    name=self.name, metadata={"hnsw:space": "cosine"}
                )
                return "chroma"
            except Exception:
                self._chroma = None
                self._client = None
        self._numpy = _NumpyVectorStore(os.path.join(self.vector_dir, self.name), self.provider.dim)
        return "numpy"

    @property
    def backend(self) -> str:
        return self._backend

    def add(self, ids: list[str], texts: list[str], metadatas: list[dict] | None = None):
        """写入：文本 → 嵌入 → 入库（去重）。"""
        existing = set(self.get_ids())
        fresh = [(i, t) for i, t in zip(ids, texts) if i not in existing]
        if not fresh:
            return
        f_ids = [i for i, _ in fresh]
        f_texts = [t for _, t in fresh]
        embeddings = self.provider.embed_sync(f_texts)
        metas = metadatas or [{}] * len(f_ids)
        if self._chroma is not None:
            self._chroma.add(ids=f_ids, documents=f_texts, embeddings=embeddings, metadatas=metas)
        else:
            self._numpy.add(f_ids, f_texts, embeddings, metas)

    def get_ids(self) -> list[str]:
        if self._chroma is not None:
            return self._chroma.get(include=[])["ids"]
        return list(self._numpy._ids)

    def query(
        self, query: str | list[float], k: int = 5, where: dict | None = None
    ) -> list[RetrievedDoc]:
        if isinstance(query, str):
            try:
                emb = self.provider.embed_sync([query])[0]
            except Exception:
                return []  # 嵌入不可用（如 API 失败）→ 返回空，由上层降级
        else:
            emb = query
        if self._chroma is not None:
            try:
                res = self._chroma.query(
                    query_embeddings=[emb],
                    n_results=min(k, max(1, self.count() or 1)),
                    where=where,
                    include=["documents", "metadatas", "distances"],
                )
                docs: list[RetrievedDoc] = []
                if res.get("ids") and res["ids"][0]:
                    for i, doc_id in enumerate(res["ids"][0]):
                        meta = (res["metadatas"][0][i] or {}) if res.get("metadatas") else {}
                        docs.append(
                            RetrievedDoc(
                                id=doc_id,
                                text=res["documents"][0][i],
                                metadata=dict(meta),
                                score=float(res["distances"][0][i]),
                            )
                        )
                return docs
            except Exception:
                pass
        return self._numpy.query(emb, k, where)

    def count(self) -> int:
        if self._chroma is not None:
            try:
                return self._chroma.count()
            except Exception:
                return 0
        return self._numpy.count()

    def delete_where(self, where: dict) -> list[str]:
        """按元数据条件删除，返回被删除的 id 列表。"""
        if self._chroma is not None:
            try:
                res = self._chroma.get(where=where, include=[])
                ids = list(res.get("ids") or [])
                if ids:
                    self._chroma.delete(ids=ids)
                return ids
            except Exception:
                pass
        # numpy 回退
        target = [
            self._numpy._ids[i]
            for i in range(len(self._numpy._ids))
            if all(self._numpy._metas[i].get(k) == v for k, v in where.items())
        ]
        if target:
            self._numpy.delete(set(target))
        return target

    def clear(self):
        """清空全部数据（用于嵌入源切换后的索引重建）。"""
        if self._chroma is not None:
            try:
                if self._client is not None:
                    self._client.delete_collection(self.name)
                    self._chroma = self._client.get_or_create_collection(
                        name=self.name, metadata={"hnsw:space": "cosine"}
                    )
                else:
                    ids = self.get_ids()
                    if ids:
                        self._chroma.delete(ids=ids)
            except Exception:
                try:
                    ids = self.get_ids()
                    if ids:
                        self._chroma.delete(ids=ids)
                except Exception:
                    pass
        else:
            self._numpy = _NumpyVectorStore(
                os.path.join(self.vector_dir, self.name), self.provider.dim
            )
