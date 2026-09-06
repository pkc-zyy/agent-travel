"""天气服务：优先 Open-Meteo 免费 API（无需 Key），带 TTL 缓存；
网络不可用时降级为基于地理纬度的本地模拟数据，保证功能完整。"""
from __future__ import annotations

import asyncio
import hashlib
import math
import time
from functools import lru_cache
from typing import Any

import httpx

from app.config import get_settings

_WEATHER_CODES: dict[int, dict[str, str]] = {
    0: {"zh": "晴", "icon": "sunny"},
    1: {"zh": "大部晴朗", "icon": "sunny"},
    2: {"zh": "多云", "icon": "cloudy"},
    3: {"zh": "阴", "icon": "cloudy"},
    45: {"zh": "雾", "icon": "fog"},
    48: {"zh": "雾凇", "icon": "fog"},
    51: {"zh": "小毛毛雨", "icon": "rain"},
    53: {"zh": "毛毛雨", "icon": "rain"},
    55: {"zh": "大毛毛雨", "icon": "rain"},
    61: {"zh": "小雨", "icon": "rain"},
    63: {"zh": "中雨", "icon": "rain"},
    65: {"zh": "大雨", "icon": "rain"},
    71: {"zh": "小雪", "icon": "snow"},
    73: {"zh": "中雪", "icon": "snow"},
    75: {"zh": "大雪", "icon": "snow"},
    80: {"zh": "阵雨", "icon": "rain"},
    81: {"zh": "强阵雨", "icon": "rain"},
    82: {"zh": "暴雨", "icon": "rain"},
    95: {"zh": "雷阵雨", "icon": "storm"},
}


def _code_label(code: int) -> str:
    return _WEATHER_CODES.get(code, {"zh": "未知", "icon": "cloudy"})


class WeatherService:
    def __init__(self):
        self.settings = get_settings()
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = asyncio.Lock()

    # ---------- 本地模拟（降级方案） ----------
    def _simulate(self, city: str, lat: float, date_str: str | None = None) -> dict:
        """基于纬度 + 日期哈希的确定性模拟天气。"""
        import datetime as dt

        month = dt.date.today().month
        if date_str:
            try:
                month = dt.date.fromisoformat(date_str).month
            except ValueError:
                pass
        base_annual = 28.0 - abs(lat) * 0.55          # 纬度越低越热
        seasonal = -7.0 * math.cos(2 * math.pi * (month - 7) / 12)  # 7月最热
        t_max = round(base_annual + seasonal + 2)
        t_min = round(base_annual + seasonal - 4)
        seed = int(hashlib.md5(f"{city}{date_str or 'today'}".encode()).hexdigest(), 16)
        conditions = ["晴", "多云", "阴", "小雨", "阵雨", "晴"]
        cond = conditions[seed % len(conditions)]
        code = {"晴": 0, "多云": 2, "阴": 3, "小雨": 61, "阵雨": 80}[cond]
        label = _code_label(code)
        return {
            "city": city,
            "date": date_str or "today",
            "condition": cond,
            "condition_en": label["icon"],
            "t_max": t_max,
            "t_min": t_min,
            "humidity": 45 + (seed % 40),
            "precip_prob": (seed % 90) if cond not in ("晴",) else (seed % 20),
            "wind": 2 + (seed % 5),
            "source": "simulated",
            "advice": self._advice(cond, t_max),
        }

    @staticmethod
    def _advice(condition: str, t_max: int) -> str:
        if condition in ("小雨", "阵雨", "大雨", "暴雨"):
            return "有降水，请携带雨具，户外行程建议备选室内方案"
        if t_max >= 30:
            return "天气炎热，注意防晒补水，午后尽量安排室内活动"
        if t_max <= 10:
            return "气温较低，注意添衣保暖"
        return "天气适宜出行，注意早晚温差"

    # ---------- 真实 API ----------
    async def _fetch_real(self, city: str, lat: float, lon: float) -> dict | None:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code,relative_humidity_2m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
            "timezone": "auto",
            "forecast_days": 7,
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.http_timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            cur = data.get("current", {})
            daily = data.get("daily", {})
            dates = daily.get("time", [])
            if not dates:
                return None
            today_code = cur.get("weather_code", daily["weather_code"][0])
            label = _code_label(today_code)
            return {
                "city": city,
                "date": dates[0],
                "condition": label["zh"],
                "condition_en": label["icon"],
                "t_max": daily["temperature_2m_max"][0],
                "t_min": daily["temperature_2m_min"][0],
                "humidity": cur.get("relative_humidity_2m"),
                "precip_prob": daily["precipitation_probability_max"][0],
                "wind": daily.get("wind_speed_10m_max", [None])[0],
                "forecast": [
                    {
                        "date": dates[i],
                        "condition": _code_label(daily["weather_code"][i])["zh"],
                        "condition_en": _code_label(daily["weather_code"][i])["icon"],
                        "t_max": daily["temperature_2m_max"][i],
                        "t_min": daily["temperature_2m_min"][i],
                        "precip_prob": daily["precipitation_probability_max"][i],
                    }
                    for i in range(len(dates))
                ],
                "source": "open-meteo",
                "advice": self._advice(label["zh"], daily["temperature_2m_max"][0]),
            }
        except Exception:
            return None

    async def get_weather(self, city: str, lat: float | None = None, lon: float | None = None,
                          date: str | None = None) -> dict[str, Any]:
        key = f"{city}|{date or 'today'}"
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and now - cached[0] < self.settings.weather_cache_ttl:
            return cached[1]

        async with self._lock:  # 防止缓存击穿
            cached = self._cache.get(key)
            if cached and now - cached[0] < self.settings.weather_cache_ttl:
                return cached[1]

            result = None
            if lat is not None and lon is not None:
                result = await self._fetch_real(city, lat, lon)
            if result is None:
                result = self._simulate(city, lat or 30.0, date)
            self._cache[key] = (time.monotonic(), result)
            return result


@lru_cache
def get_weather_service() -> WeatherService:
    return WeatherService()
