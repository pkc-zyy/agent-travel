import type { AttractionInfo, HotelInfo, WeatherInfo } from "../types";

/* ---------- 天气卡片 ---------- */
const weatherIcon: Record<string, string> = {
  sunny: "☀️",
  cloudy: "⛅",
  fog: "🌫️",
  rain: "🌧️",
  snow: "🌨️",
  storm: "⛈️",
};

export function WeatherCard({ w, compact }: { w: WeatherInfo; compact?: boolean }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-gradient-to-br from-sky-50 to-indigo-50/50 px-3.5 py-2.5">
      <span className="text-2xl">{weatherIcon[w.condition_en] ?? "🌤️"}</span>
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-slate-800">{w.city}</span>
          <span className="text-xs text-slate-500">{w.condition}</span>
        </div>
        {!compact && (
          <div className="text-xs text-slate-600">
            {w.t_min}~{w.t_max}℃ · 降水 {w.precip_prob}%
            <span className="ml-1 text-slate-400">{w.source === "open-meteo" ? "实时" : "预估"}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- 酒店卡片 ---------- */
export function HotelCard({ h }: { h: HotelInfo }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm hover:shadow transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-semibold text-slate-900 truncate">{h.name}</span>
            <span className="shrink-0 rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-600">
              ★ {h.rating}
            </span>
          </div>
          <div className="mt-0.5 text-xs text-slate-500">{h.city} · {h.budget_level ?? "综合"}</div>
        </div>
        <div className="shrink-0 text-right">
          <span className="text-sm font-bold text-brand-600">¥{h.price}</span>
          <div className="text-[10px] text-slate-400">/晚</div>
        </div>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-slate-600 line-clamp-2">{h.desc}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {h.source === "amap" && (
          <span className="rounded-md bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-600">🗺️ 高德地图</span>
        )}
        {h.source === "llm" && (
          <span className="rounded-md bg-violet-50 px-1.5 py-0.5 text-[10px] font-medium text-violet-600">✨ AI 参考</span>
        )}
        {h.tags.map((t) => (
          <span key={t} className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{t}</span>
        ))}
      </div>
      {h.address && <p className="mt-1.5 truncate text-[11px] text-slate-400" title={h.address}>📍 {h.address}</p>}
    </div>
  );
}

/* ---------- 景点卡片 ---------- */
export function AttractionCard({ a }: { a: AttractionInfo }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm hover:shadow transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-900">{a.name}</div>
          <div className="mt-0.5 text-xs text-slate-500">{a.city} · 建议 {a.duration}</div>
        </div>
        <span className="shrink-0 text-sm font-medium text-slate-600">
          {a.price > 0 ? `¥${a.price}` : "免费"}
        </span>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-slate-600 line-clamp-2">{a.desc}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {a.source === "amap" && (
          <span className="rounded-md bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-600">🗺️ 高德地图</span>
        )}
        {a.source === "llm" && (
          <span className="rounded-md bg-violet-50 px-1.5 py-0.5 text-[10px] font-medium text-violet-600">✨ AI 参考</span>
        )}
        {a.scheduled != null && (
          <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${a.scheduled ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-400"}`}>
            {a.scheduled ? "✅ 已编排" : "○ 备选"}
          </span>
        )}
        {typeof a.distance_km === "number" && a.distance_km >= 0.3 && (
          <span className="rounded-md bg-brand-50 px-1.5 py-0.5 text-[10px] font-medium text-brand-600">
            🚗 距前站约 {a.distance_km >= 100 ? Math.round(a.distance_km) : a.distance_km} km
          </span>
        )}
        {a.tags.map((t) => (
          <span key={t} className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-600">{t}</span>
        ))}
      </div>
    </div>
  );
}
