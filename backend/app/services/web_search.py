"""网页搜索服务：多 provider 降级策略。

优先级：
  1. Tavily（TAVILY_API_KEY，有免费额度）
  2. SerpAPI（SERPAPI_KEY）
  3. DuckDuckGo（免费，可能被限流）
  4. Bing HTML 抓取（免费兜底）
  5. 全部失败 → 返回空（由调用方降级到本地 RAG 知识库）

所有 provider 统一返回 [{title, url, snippet, source}]。
"""
from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
from functools import lru_cache
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _clean(text: str) -> str:
    text = html_lib.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class WebSearchService:
    def __init__(self):
        self.settings = get_settings()

    # ---------- provider：Tavily ----------
    async def _search_tavily(self, query: str, k: int) -> list[dict]:
        key = self.settings.tavily_api_key
        if not key:
            return []
        async with httpx.AsyncClient(timeout=self.settings.http_timeout) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": key, "query": query, "max_results": k, "search_depth": "basic"},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:400],
                "source": "tavily",
            }
            for r in data.get("results", [])[:k]
        ]

    # ---------- provider：SerpAPI ----------
    async def _search_serpapi(self, query: str, k: int) -> list[dict]:
        key = self.settings.serpapi_key
        if not key:
            return []
        async with httpx.AsyncClient(timeout=self.settings.http_timeout) as client:
            resp = await client.get(
                "https://serpapi.com/search.json",
                params={"engine": "google", "q": query, "api_key": key, "num": k, "hl": "zh-cn"},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("link", ""),
                "snippet": r.get("snippet", "")[:400],
                "source": "serpapi",
            }
            for r in data.get("organic_results", [])[:k]
        ]

    # ---------- provider：DuckDuckGo ----------
    async def _search_ddg(self, query: str, k: int) -> list[dict]:
        def _run():
            from duckduckgo_search import DDGS

            with DDGS() as d:
                return list(d.text(query, max_results=k))

        try:
            results = await asyncio.to_thread(_run)
        except Exception as e:  # noqa: BLE001
            logger.info("DuckDuckGo 搜索失败: %s", e)
            return []
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": (r.get("body") or "")[:400],
                "source": "duckduckgo",
            }
            for r in results[:k]
        ]

    # ---------- provider：Bing HTML 抓取 ----------
    async def _search_bing(self, query: str, k: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.settings.http_timeout, follow_redirects=True) as client:
            try:
                resp = await client.get(
                    "https://www.bing.com/search",
                    params={"q": query, "setlang": "zh-hans", "count": k},
                    headers={"User-Agent": _UA},
                )
                if resp.status_code != 200:
                    return []
                text = resp.text
            except Exception as e:  # noqa: BLE001
                logger.info("Bing 搜索失败: %s", e)
                return []

        out: list[dict] = []
        # 每个结果块：<li class="b_algo"> ... <h2><a href>标题</a></h2> ... <p>摘要</p>
        blocks = re.split(r'<li class="b_algo"', text)[1:]
        for block in blocks[: k * 2]:
            m = re.search(r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
            if not m:
                continue
            url, title = m.group(1), _clean(m.group(2))
            cap = re.search(r'class="b_caption"[^>]*>(.*?)</(?:div|p)>', block, re.S)
            snippet = _clean(cap.group(1))[:400] if cap else ""
            if title:
                out.append({"title": title, "url": url, "snippet": snippet, "source": "bing"})
            if len(out) >= k:
                break
        return out

    # ---------- 统一入口 ----------
    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """按优先级依次尝试各 provider，返回首个可用结果集。"""
        providers = [
            self._search_tavily,
            self._search_serpapi,
            self._search_ddg,
            self._search_bing,
        ]
        for provider in providers:
            try:
                results = await provider(query, top_k)
                if results:
                    return results
            except Exception as e:  # noqa: BLE001
                logger.warning("搜索 provider %s 异常: %s", provider.__name__, e)
        return []

    async def search_summary(self, query: str, top_k: int = 5) -> str:
        """返回适合注入 LLM 上下文的搜索结果摘要。"""
        results = await self.search(query, top_k)
        if not results:
            return ""
        lines = [f"「{query}」网页搜索结果："]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}（{r['source']}）\n   {r['snippet']}\n   链接：{r['url']}")
        return "\n".join(lines)


@lru_cache
def get_web_search_service() -> WebSearchService:
    return WebSearchService()
