"""嵌入提供器（方案1：语义嵌入 + 自动重建）。

- 有 LLM Key：使用 OpenAI 兼容 API 的语义嵌入（text-embedding 等），维度由模型实际返回决定；
- 无 Key 或 API 不可用：回退本地哈希嵌入（512 维，确定性）；
- 嵌入源签名 signature()：由「模式 + 模型」构成，切换 Key/模型导致签名变化时，
  上层（KnowledgeBase / LongTermMemory）据此自动重建向量索引，避免维度漂移。

维度不一致时 API 失败不静默降级哈希（维度不同会导致索引损坏），而是抛出
EmbeddingUnavailable，由调用方决定是否回退重建。
"""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache

import numpy as np

from app.services.runtime_config import is_llm_ready, resolve_llm_config

_TOKEN_RE = re.compile(r"[a-zA-Z0-9\u4e00-\u9fff]+")

# 阿里云百炼 embedding 接口单批上限为 10 条；OpenAI 等更大但取保守值以兼容各家
_EMBED_BATCH = 10


class EmbeddingUnavailable(Exception):
    """嵌入不可用（API 失败且无本地回退路径）。"""


def tokenize(text: str) -> list[str]:
    """中英文通用分词：英文按词、中文按字 + 二元组（无需第三方分词库）。"""
    text = text.lower()
    words = _TOKEN_RE.findall(text)
    tokens: list[str] = []
    for w in words:
        if w.isascii() and len(w) > 1:
            tokens.append(w)
        else:
            # 中文：单字 + 相邻二元组，捕捉语义
            tokens.extend(w)
            if len(w) >= 2:
                tokens.extend(w[i : i + 2] for i in range(len(w) - 1))
    return tokens


class HashingEmbedding:
    """离线确定性嵌入：哈希 n-gram → 有符号计数向量 → L2 归一化。"""

    def __init__(self, dim: int = 512):
        self.dim = dim

    @lru_cache(maxsize=65536)
    def _hash_token(self, tok: str) -> tuple[int, int]:
        h = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:8], "big") % self.dim
        sign = 1 if int.from_bytes(h[8:12], "big") % 2 == 0 else -1
        return idx, sign

    def embed(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float64)
        for tok in tokenize(text):
            idx, sign = self._hash_token(tok)
            vec[idx] += sign
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()


class EmbeddingProvider:
    """统一嵌入入口：API 语义嵌入（有 Key）↔ 本地哈希（无 Key）。

    由 KnowledgeBase / LongTermMemory 在构建索引时通过 activate() 显式激活
    当前嵌入模式，整批文档使用同一模式，保证维度一致；配置（Key/模型）变化
    时上层会调用 activate() 重新选择模式并重建索引。
    """

    def __init__(self):
        self._offline = HashingEmbedding()
        self._api_client = None           # 异步客户端
        self._api_sync_client = None      # 同步客户端（索引批量写入用）
        self._api_key: tuple | None = None
        self._api_dim: int | None = None  # 缓存 API 向量维度
        self._active_mode: str = "local"  # 当前激活模式

    # ---------- 模式 / 维度 / 签名 ----------
    @property
    def configured_mode(self) -> str:
        return "api" if is_llm_ready() else "local-hashing"

    @property
    def mode(self) -> str:
        return self._active_mode

    @property
    def dim(self) -> int:
        if self._active_mode == "api":
            return self._api_dim or 1536
        return self._offline.dim

    def configured_signature(self) -> tuple[str, str]:
        """配置层面的嵌入源签名（检测用户是否切换了 Key/模型）。"""
        if self.configured_mode == "api":
            return ("api", resolve_llm_config()["embedding_model"])
        return ("local", "")

    def activate(self, mode: str) -> None:
        """激活嵌入模式：'api' 或 'local'。"""
        self._active_mode = "api" if mode == "api" else "local"

    def probe_api(self) -> bool:
        """探测 API 嵌入是否可用（发一个最小请求），可用则缓存维度。"""
        try:
            vecs = self._embed_api_sync(["embedding_probe"])
            return bool(vecs and vecs[0])
        except Exception:
            self._api_dim = None
            return False

    # ---------- API 客户端 ----------
    def _cfg(self) -> dict:
        return resolve_llm_config()

    def _get_async_client(self):
        from openai import AsyncOpenAI

        cfg = self._cfg()
        key = (cfg["api_key"], cfg["base_url"])
        if self._api_client is None or self._api_key != key:
            self._api_client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
            self._api_key = key
        return self._api_client

    def _get_sync_client(self):
        from openai import OpenAI

        cfg = self._cfg()
        key = (cfg["api_key"], cfg["base_url"])
        if self._api_sync_client is None or self._api_key != key:
            self._api_sync_client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
            self._api_key = key
        return self._api_sync_client

    # ---------- 嵌入实现 ----------
    async def _embed_api(self, texts: list[str]) -> list[list[float]]:
        model = self._cfg()["embedding_model"]
        client = self._get_async_client()
        vecs: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH):
            batch = texts[i : i + _EMBED_BATCH]
            resp = await client.embeddings.create(model=model, input=batch)
            ordered = sorted(resp.data, key=lambda d: d.index)
            vecs.extend(d.embedding for d in ordered)
        if vecs:
            self._api_dim = len(vecs[0])
        return vecs

    def _embed_api_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._cfg()["embedding_model"]
        client = self._get_sync_client()
        vecs: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH):
            batch = texts[i : i + _EMBED_BATCH]
            resp = client.embeddings.create(model=model, input=batch)
            ordered = sorted(resp.data, key=lambda d: d.index)
            vecs.extend(d.embedding for d in ordered)
        if vecs:
            self._api_dim = len(vecs[0])
        return vecs

    # ---------- 对外接口 ----------
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._active_mode == "api" and texts:
            try:
                return await self._embed_api(texts)
            except Exception as e:  # noqa: BLE001
                raise EmbeddingUnavailable(f"API 嵌入失败: {e}") from e
        return [self._offline.embed(t) for t in texts]

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        """同步版本（chromadb 批量写入）。API 失败抛 EmbeddingUnavailable。"""
        if self._active_mode == "api" and texts:
            try:
                return self._embed_api_sync(texts)
            except Exception as e:  # noqa: BLE001
                raise EmbeddingUnavailable(f"API 嵌入失败: {e}") from e
        return [self._offline.embed(t) for t in texts]


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return EmbeddingProvider()
