"""设置 API：用户在界面上接入自己的 LLM API（实时生效，无需重启）。"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.runtime_config import (
    get_runtime_config,
    is_llm_ready,
    mask_key,
    resolve_amap_key,
    resolve_llm_config,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


class LlmSettingsIn(BaseModel):
    provider: str = Field("custom", description="openai | deepseek | custom")
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    embedding_model: str = ""


class LlmTestIn(BaseModel):
    provider: str = "custom"
    api_key: str = ""
    base_url: str = ""
    model: str = ""


def _public_config() -> dict:
    cfg = resolve_llm_config()
    return {
        "provider": cfg["provider"],
        "api_key_masked": mask_key(cfg["api_key"]),
        "has_key": bool(cfg["api_key"]),
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "embedding_model": cfg["embedding_model"],
        "source": cfg["source"],
        "ready": is_llm_ready(),
        "mode": "llm" if is_llm_ready() else "offline",
    }


@router.get("/llm")
async def get_llm_settings():
    return _public_config()


@router.post("/llm")
async def save_llm_settings(body: LlmSettingsIn):
    """保存 LLM 配置；api_key 置空表示清除运行时配置（回退到 .env）。"""
    runtime = get_runtime_config()
    if body.api_key.strip():
        runtime.set_llm(
            {
                "provider": body.provider,
                "api_key": body.api_key.strip(),
                "base_url": body.base_url.strip(),
                "model": body.model.strip(),
                "embedding_model": body.embedding_model.strip(),
            }
        )
    else:
        runtime.clear_llm()
    return _public_config()


@router.post("/llm/test")
async def test_llm(body: LlmTestIn):
    """用给定（或已保存）的配置做一次最小对话请求，验证连通性。"""
    cfg = resolve_llm_config()
    api_key = body.api_key.strip() or cfg["api_key"]
    if not api_key:
        return {"ok": False, "message": "未提供 API Key"}

    base_url = body.base_url.strip() or cfg["base_url"] or "https://api.openai.com/v1"
    model = body.model.strip() or cfg["model"] or "gpt-4o-mini"

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=20.0)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "回复：OK"}],
            max_tokens=8,
        )
        content = (resp.choices[0].message.content or "").strip()[:40]
        return {"ok": True, "message": f"连接成功（模型 {model}）：{content or '已响应'}"}
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM 连接测试失败: %s", e)
        msg = str(e)
        hint = _diagnose(msg, base_url, model)
        return {"ok": False, "message": hint}


def _diagnose(msg: str, base_url: str, model: str) -> str:
    """根据错误信息给出可操作的排查建议。"""
    low = msg.lower()
    if "401" in msg or "invalid api key" in low or "authentication" in low or "unauthorized" in low:
        return f"API Key 无效或被拒绝。请确认 Key 正确、未过期、已开通对应服务。（错误：{msg[:200]}）"
    if "404" in msg or "not found" in low or "model_not_found" in low:
        return (
            f"模型「{model}」不存在或接口地址错误。请检查：\n"
            f"  - Base URL 是否正确：{base_url}\n"
            f"  - 模型名是否是该服务商支持的模型\n"
            f"  - 阿里云百炼应填 base_url=https://dashscope.aliyuncs.com/compatible-mode/v1，模型如 qwen-plus"
        )
    if "connection" in low or "timeout" in low or "connect" in low or "timed out" in low:
        return f"无法连接到 {base_url}。请检查网络，或确认 Base URL 地址正确（错误：{msg[:160]}）"
    if "insufficient" in low or "quota" in low or "balance" in low or "429" in msg:
        return f"额度不足或请求被限流（可能未开通服务/欠费）。请到控制台确认已开通并充值。（错误：{msg[:160]}）"
    return f"连接失败：{msg[:300]}。如为阿里云百炼，请确认 Base URL 为 https://dashscope.aliyuncs.com/compatible-mode/v1，模型为 qwen-plus。"


# ==================== 高德地图（酒店 POI / 地理编码） ====================
class AmapSettingsIn(BaseModel):
    api_key: str = ""


@router.get("/amap")
async def get_amap_settings():
    key = resolve_amap_key()
    return {
        "api_key_masked": mask_key(key),
        "has_key": bool(key),
        "source": "runtime" if get_runtime_config().get_amap().get("api_key") else ("env" if key else "none"),
        "ready": bool(key),
    }


@router.post("/amap")
async def save_amap_settings(body: AmapSettingsIn):
    """保存/清除高德 Key；api_key 为空表示清除（回退 .env 或本地数据）。"""
    runtime = get_runtime_config()
    if body.api_key.strip():
        runtime.set_amap(body.api_key.strip())
    else:
        runtime.clear_amap()
    return await get_amap_settings()


@router.post("/amap/test")
async def test_amap(body: AmapSettingsIn):
    """用给定（或已保存）Key 做一次地理编码，验证连通性。"""
    from app.services.amap import get_amap_service

    if body.api_key.strip():
        get_runtime_config().set_amap(body.api_key.strip())
    svc = get_amap_service()
    if not svc.is_ready():
        return {"ok": False, "message": "未提供高德 API Key"}

    try:
        loc = await svc.geocode("北京市")
        if loc:
            return {
                "ok": True,
                "message": f"连接成功：北京中心点坐标 ({loc['lat']}, {loc['lon']})，酒店 POI 检索可用",
            }
        return {"ok": False, "message": "Key 已连通但地理编码无结果，请确认 Key 类型为「Web服务」"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"连接失败：{e}"}
