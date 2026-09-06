import type { PlanData } from "../types";
import { AttractionCard, HotelCard, WeatherCard } from "./Cards";

/** 完整行程方案可视化：概览 → 日程时间线 → 酒店/景点/天气/预算 */
export default function PlanView({ plan }: { plan: PlanData }) {
  return (
    <div className="space-y-5">
      {/* 概览 */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-bold text-slate-900">{plan.title}</h3>
            <p className="mt-1 text-sm text-slate-600">{plan.summary}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className={`rounded-full px-3 py-1 text-xs font-medium ${plan.review.passed ? "bg-emerald-50 text-emerald-600" : "bg-amber-50 text-amber-600"}`}>
              {plan.review.passed ? "✅ 质量审查通过" : "⚠️ 审查有优化建议"} · {plan.review.score} 分
            </span>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetaItem icon="🗺️" label="城市路线" value={plan.cities.join(" → ")} />
          <MetaItem icon="📅" label="行程天数" value={`${plan.days} 天`} />
          <MetaItem icon="💰" label="预算范围" value={plan.budget_range || "待定"} />
          <MetaItem icon="👥" label="出行人员" value={plan.travelers || "未指定"} />
        </div>
      </div>

      {/* 每日行程时间线 */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <SectionTitle icon="🗓️" title="每日行程" />
        <div className="mt-4 space-y-4">
          {plan.schedule.map((d) => (
            <div key={d.day} className="relative flex gap-4">
              {/* 时间线圆点 */}
              <div className="flex flex-col items-center">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-50 text-sm font-bold text-brand-600 ring-1 ring-brand-200">
                  D{d.day}
                </div>
                {d.day < plan.schedule.length && <div className="mt-1 w-px flex-1 bg-slate-200" />}
              </div>
              {/* 当日内容 */}
              <div className="min-w-0 flex-1 pb-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-bold text-slate-900">{d.city}</span>
                  <span className="text-xs text-slate-500">· {d.title}</span>
                  {d.weather && <WeatherCard w={d.weather} compact />}
                </div>
                {d.transport && <div className="mt-1.5 text-xs text-slate-500">🚄 {d.transport}</div>}
                {d.route_summary && (
                  <div className="mt-1.5 rounded-lg bg-slate-50 px-3 py-1.5 text-xs text-slate-600">
                    🧭 当日动线：{d.route_summary}
                  </div>
                )}
                <ul className="mt-2 space-y-1">
                  {d.activities.map((act, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-[13px] text-slate-700">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brand-400" />
                      {act}
                    </li>
                  ))}
                </ul>
                <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
                  {d.attractions.map((a) => (
                    <AttractionCard key={a.name} a={a} />
                  ))}
                  {d.hotel && <HotelCard h={d.hotel} />}
                </div>
                {d.meals.length > 0 && (
                  <div className="mt-2 text-xs text-slate-500">
                    🍜 推荐美食：{d.meals.join("、")}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 天气汇总 */}
      {plan.weather.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <SectionTitle icon="☀️" title="目的地天气" />
          <div className="mt-3 flex flex-wrap gap-2">
            {plan.weather.map((w) => (
              <WeatherCard key={w.city} w={w} />
            ))}
          </div>
        </div>
      )}

      {/* 酒店汇总 */}
      {plan.hotels.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <SectionTitle icon="🏨" title="酒店推荐汇总" />
          {plan.hotel_strategy && Object.keys(plan.hotel_strategy).length > 0 && (
            <p className="mt-1.5 text-xs text-slate-500">
              🧭 已按「贴近景点群」自动选址：
              {Object.entries(plan.hotel_strategy)
                .filter(([, s]) => s.avg_km != null)
                .map(([city, s]) => `${city} 平均距景点约 ${s.avg_km} km`)
                .join("，")}
            </p>
          )}
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {plan.hotels.map((h) => (
              <HotelCard key={h.name} h={h} />
            ))}
          </div>
        </div>
      )}

      {/* 景点汇总 */}
      {plan.attractions.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <SectionTitle icon="🏔️" title="景点推荐汇总" />
          <p className="mt-1.5 text-xs text-slate-500">✅ = 已编入每日行程　○ = 备选（可替换到行程中）</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {plan.attractions.map((a) => (
              <AttractionCard key={a.name} a={a} />
            ))}
          </div>
        </div>
      )}

      {/* 预算 */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <SectionTitle icon="💰" title="预算明细（人均估算）" />
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <BudgetItem label="城际交通" value={plan.budget.transport} />
          <BudgetItem label="住宿" value={plan.budget.hotel} />
          <BudgetItem label="餐饮" value={plan.budget.food} />
          <BudgetItem label="门票" value={plan.budget.tickets} />
        </div>
        <div className="mt-3 rounded-xl bg-brand-50 px-4 py-2.5 text-sm text-brand-800">
          合计约 <span className="text-lg font-bold">¥{plan.budget.total_per_person}</span> / 人
        </div>
      </div>

      {/* 贴士 */}
      {plan.tips.length > 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <SectionTitle icon="💡" title="温馨提示" />
          <ul className="mt-2 space-y-1.5">
            {plan.tips.map((t, i) => (
              <li key={i} className="flex items-start gap-2 text-[13px] text-slate-700">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-amber-400" />
                {t}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 协作智能体 */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <SectionTitle icon="🤖" title="本次协作的智能体" />
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {plan.agents.map((a) => (
            <div key={a.name} className="flex items-center gap-2.5 rounded-xl bg-slate-50 px-3 py-2">
              <span className="text-xl">{a.emoji}</span>
              <div className="min-w-0">
                <div className="text-[13px] font-semibold text-slate-800">{a.name}</div>
                <div className="truncate text-[11px] text-slate-500">{a.role}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SectionTitle({ icon, title }: { icon: string; title: string }) {
  return (
    <h4 className="flex items-center gap-2 text-[15px] font-bold text-slate-900">
      <span>{icon}</span>
      {title}
    </h4>
  );
}

function MetaItem({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-2.5">
      <div className="text-[11px] text-slate-400">{icon} {label}</div>
      <div className="mt-0.5 truncate text-[13px] font-semibold text-slate-800" title={value}>{value}</div>
    </div>
  );
}

function BudgetItem({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5 text-center">
      <div className="text-[11px] text-slate-400">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-slate-800">约 ¥{value}</div>
    </div>
  );
}
