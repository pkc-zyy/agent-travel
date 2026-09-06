"""运行时动态配置：用户在界面上保存的配置（LLM API 等），持久化到 JSON 文件。

优先级：运行时配置（前端「设置」页保存） > 环境变量（.env）。
所有读取函数实时解析（不做跨请求缓存），因此前端保存后立即生效，无需重启。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.config import get_settings

_PROVIDER_DEFAULTS = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "embedding_model": ""},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "embedding_model": "text-embedding-3-small"},
    "aliyun": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "embedding_model": "text-embedding-v3",
    },
}


class RuntimeConfigManager:
    def __init__(self):
        self._settings = get_settings()
        self._path: Path = self._settings.data_dir / "runtime_config.json"
        self._lock = threading.Lock()
        self._cache: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._cache = data if isinstance(data, dict) else {}
            else:
                self._cache = {}
        except Exception:
            self._cache = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------- LLM 配置读写 ----------
    def get_llm(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._cache.get("llm", {}))

    def set_llm(self, data: dict[str, Any]) -> dict[str, Any]:
        """保存 LLM 配置，返回归一化后的结果。"""
        with self._lock:
            llm = dict(self._cache.get("llm", {}))
            for key in ("provider", "api_key", "base_url", "model", "embedding_model"):
                if key in data:
                    val = data[key]
                    llm[key] = (val or "").strip() if isinstance(val, str) else ""
            self._cache["llm"] = llm
            self._save()
            return dict(llm)

    def clear_llm(self) -> None:
        with self._lock:
            self._cache.pop("llm", None)
            self._save()

    # ---------- 高德地图配置读写 ----------
    def get_amap(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._cache.get("amap", {}))

    def set_amap(self, api_key: str) -> dict[str, Any]:
        with self._lock:
            amap = dict(self._cache.get("amap", {}))
            amap["api_key"] = (api_key or "").strip()
            self._cache["amap"] = amap
            self._save()
            return dict(amap)

    def clear_amap(self) -> None:
        with self._lock:
            self._cache.pop("amap", None)
            self._save()


_runtime: RuntimeConfigManager | None = None
_lock = threading.Lock()


def get_runtime_config() -> RuntimeConfigManager:
    global _runtime
    with _lock:
        if _runtime is None:
            _runtime = RuntimeConfigManager()
        return _runtime


def resolve_llm_config() -> dict[str, Any]:
    """合并运行时配置与环境变量，返回最终生效的 LLM 配置（每次实时解析）。"""
    s = get_settings()
    rt = get_runtime_config().get_llm()
    rt_key = (rt.get("api_key") or "").strip()

    if rt_key:
        provider = (rt.get("provider") or "custom").strip() or "custom"
        defaults = _PROVIDER_DEFAULTS.get(provider, {"base_url": "", "model": "", "embedding_model": ""})
        return {
            "provider": provider,
            "api_key": rt_key,
            "base_url": (rt.get("base_url") or "").strip() or defaults.get("base_url", ""),
            "model": (rt.get("model") or "").strip() or defaults.get("model", ""),
            "embedding_model": (rt.get("embedding_model") or "").strip()
            or defaults.get("embedding_model", "")
            or s.embedding_model,
            "source": "runtime",
        }

    if s.deepseek_api_key:
        return {
            "provider": "deepseek",
            "api_key": s.deepseek_api_key,
            "base_url": s.llm_base_url or _PROVIDER_DEFAULTS["deepseek"]["base_url"],
            "model": s.llm_model or _PROVIDER_DEFAULTS["deepseek"]["model"],
            "embedding_model": s.embedding_model,
            "source": "env",
        }

    if s.openai_api_key:
        return {
            "provider": "openai",
            "api_key": s.openai_api_key,
            "base_url": s.llm_base_url or _PROVIDER_DEFAULTS["openai"]["base_url"],
            "model": s.llm_model or _PROVIDER_DEFAULTS["openai"]["model"],
            "embedding_model": s.embedding_model,
            "source": "env",
        }

    return {
        "provider": "offline",
        "api_key": "",
        "base_url": "",
        "model": "",
        "embedding_model": s.embedding_model,
        "source": "none",
    }


def is_llm_ready() -> bool:
    return bool(resolve_llm_config()["api_key"])


def resolve_amap_key() -> str:
    """高德 Key：运行时配置（设置页保存）> 环境变量（.env）。"""
    rt = get_runtime_config().get_amap()
    return (rt.get("api_key") or "").strip() or get_settings().amap_api_key


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}****{key[-4:]}"
