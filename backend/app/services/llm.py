"""LLM 客户端：OpenAI 兼容协议。
- 配置了 Key（运行时配置或 .env）：真实 LLM 推理，支持流式。
- 未配置：离线模板引擎（确定性输出），保证全流程可运行。

配置来源优先级：前端「设置」页保存的运行时配置 > 环境变量(.env)。
配置实时生效：每次调用前重新解析，切换 Key 无需重启。
"""
from __future__ import annotations

import json
import logging
import re
import time
from functools import lru_cache
from typing import Any

from app.services.monitor import get_monitor
from app.services.runtime_config import is_llm_ready, resolve_llm_config

logger = logging.getLogger(__name__)


class FallbackEngine:
    """离线模板引擎：对常见问题给出结构化、可用的回答。"""

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.3) -> str:
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break
        text = user_text.strip()[:80]
        return (
            f"（离线模式）已收到您的需求：「{text}」。\n\n"
            "当前未配置 LLM API Key，智能体正在使用内置知识库与规则引擎为您服务。\n"
            "您可以继续描述目的地、天数、预算与偏好，例如：\n"
            "- 「帮我规划云南昆明-大理-丽江 5 日游，人均 4000」\n"
            "- 「北京 3 天怎么玩」\n"
            "- 「推荐丽江适合情侣的酒店」\n\n"
            "配置方式：点击右上角「⚙️ 设置」填入您的 LLM API Key（OpenAI / DeepSeek / 自定义网关），保存后立即生效。"
        )


class LLMClient:
    def __init__(self):
        self._client = None
        self._client_key: tuple | None = None
        self._fallback = FallbackEngine()

    @property
    def mode(self) -> str:
        return "llm" if is_llm_ready() else "offline"

    @staticmethod
    def _cfg() -> dict[str, Any]:
        return resolve_llm_config()

    def _get_client(self):
        cfg = self._cfg()
        key = (cfg["api_key"], cfg["base_url"])
        if self._client is None or self._client_key != key:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
            self._client_key = key
        return self._client

    async def chat(self, messages: list[dict[str, str]], temperature: float = 0.3,
                   max_tokens: int = 1200, stream: bool = False) -> str | Any:
        """调用 LLM。stream=False 返回完整文本；stream=True 返回异步生成器。"""
        monitor = get_monitor()
        started = time.monotonic()
        prompt_chars = sum(len(m.get("content", "")) for m in messages)

        if self.mode == "offline":
            output = self._fallback.chat(messages, temperature)
            monitor.record("llm", "offline-template", {
                "mode": "offline",
                "prompt_chars": prompt_chars,
                "output": output[:150],
            }, (time.monotonic() - started) * 1000)
            return output

        model = self._cfg()["model"]
        client = self._get_client()
        try:
            if stream:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
                return resp
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            output = resp.choices[0].message.content or ""
            usage = getattr(resp, "usage", None)
            monitor.record("llm", model, {
                "mode": "llm",
                "prompt_chars": prompt_chars,
                "output": output[:150],
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
            }, (time.monotonic() - started) * 1000)
            return output
        except Exception as e:
            logger.warning("LLM 调用失败，降级为离线模式: %s", e)
            monitor.record("llm", model, {
                "mode": "llm",
                "prompt_chars": prompt_chars,
                "error": str(e)[:300],
            }, (time.monotonic() - started) * 1000, status="error")
            return self._fallback.chat(messages, temperature)

    async def chat_json(self, messages: list[dict[str, str]], temperature: float = 0.0,
                        retries: int = 2) -> dict | None:
        """要求 LLM 输出 JSON 对象。"""
        if self.mode == "offline":
            return None
        prompt = messages[-1]["content"] if messages else ""
        messages = [*messages[:-1], {"role": "user", "content": prompt + "\n\n只输出 JSON，不要输出其他内容。"}]
        for _ in range(retries):
            text = await self.chat(messages, temperature=temperature, max_tokens=2000)
            if isinstance(text, str):
                parsed = self._extract_json(text)
                if parsed is not None:
                    return parsed
        return None

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


@lru_cache
def get_llm_client() -> LLMClient:
    return LLMClient()
