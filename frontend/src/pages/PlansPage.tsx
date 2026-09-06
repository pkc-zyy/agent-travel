import { useEffect, useState } from "react";
import { api, getUserId } from "../api/client";
import type { TripDetail, TripItem } from "../types";
import Markdown from "../components/Markdown";
import PlanView from "../components/PlanView";

const userId = getUserId();

export default function PlansPage() {
  const [plans, setPlans] = useState<TripItem[]>([]);
  const [detail, setDetail] = useState<TripDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [err, setErr] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      setPlans(await api.listPlans(userId));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openDetail = async (id: number) => {
    setDetailLoading(true);
    setErr("");
    try {
      setDetail(await api.getPlan(id));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setDetailLoading(false);
    }
  };

  const remove = async (id: number) => {
    if (!confirm("确定删除该行程方案吗？")) return;
    await api.deletePlan(id);
    if (detail?.id === id) setDetail(null);
    load();
  };

  return (
    <div className="flex h-full gap-5 p-5 sm:p-6">
      {/* 左侧：方案列表 */}
      <div className={`flex h-full min-w-0 flex-col ${detail ? "w-80 shrink-0" : "w-full max-w-xl mx-auto"}`}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-900">我的行程</h2>
          <button onClick={load} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 shadow-sm hover:border-brand-300">
            ⟳ 刷新
          </button>
        </div>
        {err && <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-500">{err}</div>}
        <div className="flex-1 space-y-3 overflow-y-auto pr-1">
          {loading && <p className="text-sm text-slate-400">加载中…</p>}
          {!loading && plans.length === 0 && (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
              <div className="text-3xl">🗺️</div>
              <p className="mt-2 text-sm text-slate-500">还没有保存的行程</p>
              <p className="mt-1 text-xs text-slate-400">去「智能规划」让智能体团队为您生成一份方案吧</p>
            </div>
          )}
          {plans.map((p) => (
            <div
              key={p.id}
              onClick={() => openDetail(p.id)}
              className={`cursor-pointer rounded-2xl border bg-white p-4 shadow-sm transition hover:shadow-md ${
                detail?.id === p.id ? "border-brand-400 ring-2 ring-brand-100" : "border-slate-200"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-900">{p.title}</div>
                  <div className="mt-0.5 truncate text-xs text-slate-500">{p.request}</div>
                </div>
                {p.rating > 0 && (
                  <span className="shrink-0 rounded-lg bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-600">
                    ★ {p.rating.toFixed(1)}
                  </span>
                )}
              </div>
              <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400">
                <span>🗺️ {p.cities.join(" → ")}</span>
                <span>📅 {p.days} 天</span>
                <span>💰 {p.budget || "—"}</span>
                <span className="ml-auto">{new Date(p.created_at).toLocaleDateString("zh-CN")}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 右侧：方案详情 */}
      {detail && (
        <div className="min-w-0 flex-1 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-bold text-slate-900">{detail.title}</h3>
              <p className="mt-0.5 text-xs text-slate-500">生成于 {new Date(detail.created_at).toLocaleString("zh-CN")}</p>
            </div>
            <button onClick={() => remove(detail.id)} className="shrink-0 rounded-lg border border-red-200 px-3 py-1.5 text-xs text-red-500 hover:bg-red-50">
              删除
            </button>
          </div>
          {detailLoading ? (
            <p className="py-10 text-center text-sm text-slate-400">加载方案详情…</p>
          ) : detail.plan ? (
            <div className="space-y-4">
              <PlanView plan={detail.plan} />
              <details className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
                <summary className="cursor-pointer text-sm font-semibold text-slate-700">📄 查看完整 Markdown 方案</summary>
                <div className="mt-3"><Markdown content={detail.markdown ?? ""} /></div>
              </details>
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-200 p-6">
              <Markdown content={detail.markdown ?? "（无方案内容）"} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
