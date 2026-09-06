"""全局配置：环境变量 + 默认值，统一从这里读取。"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent          # backend/
PROJECT_DIR = BACKEND_DIR.parent                             # 项目根
DATA_DIR = BACKEND_DIR / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
VECTOR_DIR = DATA_DIR / "vectors"
DB_PATH = DATA_DIR / "travel.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # 应用
    app_name: str = "TravelAgent 多智能体旅行规划平台"
    api_prefix: str = "/api"
    debug: bool = True

    # LLM（OpenAI 兼容）
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    embedding_model: str = "text-embedding-3-small"

    # 网页搜索（可选 Key，未配置则用免费 DuckDuckGo / Bing 兜底）
    tavily_api_key: str = ""
    serpapi_key: str = ""

    # 高德地图（可选 Key：真实酒店 POI / 地理编码 / 周边搜索；未配置回退本地知识库）
    amap_api_key: str = ""

    # 数据库
    database_url: str = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

    # 服务
    weather_cache_ttl: int = 600          # 天气缓存秒数
    http_timeout: float = 12.0            # 外部 HTTP 超时

    # 检索
    vector_top_k: int = 8                 # 向量召回数量
    bm25_top_k: int = 8                   # BM25 召回数量
    rag_final_k: int = 5                  # 混合融合后最终数量
    memory_top_k: int = 4                 # 长期记忆召回数量

    # 会话
    session_window: int = 12              # 短期记忆保留的消息条数
    context_max_chars: int = 9000         # 上下文包字符预算

    # 提示词（留空则使用内置默认，见 app/prompts.py；可用 .env 的 PROMPT_* 覆盖）
    prompt_system: str = ""
    prompt_summary: str = ""
    prompt_planner_parse: str = ""
    prompt_feedback_lessons: str = ""
    prompt_memory_extract: str = ""
    prompt_mcp_instructions: str = ""

    # 路径
    data_dir: Path = DATA_DIR
    knowledge_dir: Path = KNOWLEDGE_DIR
    vector_dir: Path = VECTOR_DIR

    # ---------- 派生属性 ----------
    @property
    def llm_ready(self) -> bool:
        """是否配置了真实 LLM（任一 Key 可用即视为就绪）。"""
        return bool(self.openai_api_key or self.deepseek_api_key)

    @property
    def active_api_key(self) -> str:
        return self.deepseek_api_key or self.openai_api_key

    @property
    def active_base_url(self) -> str:
        if self.llm_base_url:
            return self.llm_base_url
        if self.deepseek_api_key:
            return "https://api.deepseek.com/v1"
        return "https://api.openai.com/v1"

    @property
    def active_model(self) -> str:
        if self.llm_model:
            return self.llm_model
        if self.deepseek_api_key:
            return "deepseek-chat"
        return "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # 确保目录存在
    for p in (s.data_dir, s.knowledge_dir, s.vector_dir):
        p.mkdir(parents=True, exist_ok=True)
    return s
