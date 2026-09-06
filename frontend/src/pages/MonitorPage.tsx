import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { MonitorEvent } from "../types";

const TYPE_META: Record<string, { label: string; icon: string; cls: string }> = {
  tool: { label: "工具调用", icon: "🔧", cls: "bg-violet-50 text-violet-600 ring-violet-200" },
  llm: { label: "LLM 调用", icon: "🧠", cls: "bg-indigo-50 text-indigo-600 ring-indigo-200" },
};

type FilterKey = "all" | "tool" | "llm";

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: "all", label: "全部" },
  { key: "tool", label: "🔧 工具" },
  { key: "llm", label: "🧠 LLM" },
];

function isTracked(ev: MonitorEvent): boolean {
  return ev.type === "tool" || ev.type === "llm";
}

export default function MonitorPage() {
  const [events, setEvents] = useState<MonitorEvent[]>([]);
  const [counts, setCounts] = useState<Record<string, { total: number; errors: number; avg: number | null }>>({});
  const [filter, setFilter] = useState<FilterKey>("all");
  const [live, setLive] = useState(true);
  const [connected, setConnected] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [ev, sum] = await Promise.all([
        api.monitorEvents({ limit: 300 }),
        api.monitorSummary(),
      ]);
      const tracked = ev.events.filter(isTracked);
      setEvents(tracked);
      setCounts({
        tool: {
          total: sum.by_type.tool?.total ?? 0,
          errors: sum.by_type.tool?.errors ?? 0,
          avg: sum.avg_ms.tool ?? null,
        },
        llm: {
          total: sum.by_type.llm?.total ?? 0,
          errors: sum.by_type.llm?.errors ?? 0,
          avg: sum.avg_ms.llm ?? null,
        },
      });
    } catch {
      /* 静默 */
    }
  }, []);

  // 实时订阅：只接收 工具/LLM 事件
  useEffect(() => {
    if (!live) {
      abortRef.current?.abort();
      abortRef.current = null;
      setConnected(false);
      return;
    }
    const abort = new AbortController();
    abortRef.current = abort;
    api
      .monitorStream(
        (ev) => {
          if (!isTracked(ev)) return;
          setConnected(true);
          setEvents((prev) => [ev, ...prev].slice(0, 300));
          setCounts((c) => ({
            ...c,
            [ev.type]: {
              total: (c[ev.type]?.total ?? 0) + 1,
              errors: (c[ev.type]?.errors ?? 0) + (ev.status === "error" ? 1 : 0),
              avg: c[ev.type]?.avg ?? null,
            },
          }));
        },
        abort.signal
      )
      .then(() => setConnected(false))
      .catch(() => setConnected(false));
    return () => abort.abort();
  }, [live]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const visible = filter === "all" ? events : events.filter((e) => e.type === filter);
  const toolCount = counts.tool ?? { total: 0, errors: 0, avg: null };
  const llmCount = counts.llm ?? { total: 0, errors: 0, avg: null };

  return (
    <div className="h-full overflow-y-auto p-5 sm:p-6">
      {/* 头部 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 text-xl text-white shadow">
            📡
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">运行监控</h2>
            <p className="text-sm text-slate-500">实时监测工具调用与 LLM 调用次数及输出结果</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${
              live && connected ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-500"
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${live && connected ? "animate-pulse bg-emerald-500" : "bg-slate-400"}`} />
            {live && connected ? "实时监听中" : live ? "连接中…" : "已暂停"}
          </span>
          <button
            onClick={() => setLive((v) => !v)}
            className={`rounded-xl px-3.5 py-1.5 text-xs font-medium shadow-sm transition ${
              live ? "bg-slate-200 text-slate-600 hover:bg-slate-300" : "bg-emerald-600 text-white hover:bg-emerald-700"
            }`}
          >
            {live ? "⏸ 暂停监听" : "▶ 开启实时"}
          </button>
          <button
            onClick={refresh}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition hover:bg-slate-50"
          >
            ↻ 刷新
          </button>
        </div>
      </div>

      {/* 只有两张统计卡片：工具调用 / LLM 调用 */}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <CountCard icon="🔧" label="工具调用" accent="from-violet-500 to-fuchsia-500" data={toolCount} />
        <CountCard icon="🧠" label="LLM 调用" accent="from-indigo-500 to-sky-500" data={llmCount} />
      </div>

      {/* 过滤 */}
      <div className="mt-4 flex items-center gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-xl px-3.5 py-1.5 text-xs font-medium transition ${
              filter === f.key
                ? "bg-brand-600 text-white shadow-sm"
                : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* 事件列表 */}
      <div className="mt-3 space-y-2 pb-6">
        {visible.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-400">
            暂无调用记录 —— 去对话页发起一次规划，工具与 LLM 的每次调用都会出现在这里。
          </div>
        )}
        {visible.map((ev) => {
          const meta = TYPE_META[ev.type];
          const open = expanded === ev.id;
          return (
            <button
              key={ev.id}
              onClick={() => setExpanded(open ? null : ev.id)}
              className="block w-full rounded-xl border border-slate-100 bg-white p-3 text-left shadow-sm transition hover:border-slate-200"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ${meta.cls}`}>
                  {meta.icon} {meta.label}
                </span>
                <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-slate-800">{ev.name}</span>
                {ev.duration_ms != null && (
                  <span className={`text-[11px] ${ev.duration_ms > 3000 ? "font-bold text-amber-600" : "text-slate-400"}`}>
                    {ev.duration_ms} ms
                  </span>
                )}
                {ev.status === "error" && (
                  <span className="rounded-md bg-red-50 px-2 py-0.5 text-[11px] font-bold text-red-500">错误</span>
                )}
                <span className="text-[11px] text-slate-400">{new Date(ev.ts).toLocaleTimeString("zh-CN")}</span>
              </div>
              {open && ev.detail && (
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-600">
                  {JSON.stringify(ev.detail, null, 2)}
                </pre>
              )}
              {!open && ev.detail && (
                <p className="mt-1 truncate text-[11px] text-slate-400">
                  {String(ev.detail.output ?? ev.detail.error ?? JSON.stringify(ev.detail)).slice(0, 120)}
                </p>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function CountCard({
  icon,
  label,
  accent,
  data,
}: {
  icon: string;
  label: string;
  accent: string;
  data: { total: number; errors: number; avg: number | null };
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-500">
          <span className={`flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br ${accent} text-base text-white`}>
            {icon}
          </span>
          {label}
        </div>
        {data.errors > 0 && (
          <span className="rounded-full bg-red-50 px-2.5 py-0.5 text-[11px] font-medium text-red-500">{data.errors} 次错误</span>
        )}
      </div>
      <div className="mt-2 flex items-end gap-3">
        <span className="text-3xl font-bold text-slate-900">{data.total}</span>
        <span className="pb-1 text-xs text-slate-400">次</span>
        {data.avg != null && <span className="pb-1 text-xs text-slate-400">平均 {data.avg} ms</span>}
      </div>
    </div>
  );
}
