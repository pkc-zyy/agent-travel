import { useState } from "react";
import type { AgentEvent } from "../types";

/** 智能体协作过程面板：展示主管如何调度各专家 Agent */
export default function AgentTrace({
  events,
  open,
  onToggle,
}: {
  events: AgentEvent[];
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
      >
        <span className="flex items-center gap-2 text-[13px] font-semibold text-slate-700">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-brand-500" />
          </span>
          智能体协作过程
          <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
            {events.length}
          </span>
        </span>
        <span className="text-slate-400 text-xs">{open ? "收起 ▲" : "展开 ▼"}</span>
      </button>
      {open && (
        <div className="max-h-64 space-y-1 overflow-y-auto border-t border-slate-100 px-4 py-3">
          {events.length === 0 && (
            <p className="text-xs text-slate-400">发送消息后，这里将实时展示各智能体的协作过程…</p>
          )}
          {events.map((ev, i) => (
            <div key={i} className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50">
              <span className="text-base leading-6">{ev.emoji}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-semibold text-slate-800">{ev.name}</span>
                  <span
                    className={`rounded px-1.5 py-px text-[10px] font-medium ${
                      ev.status === "done"
                        ? "bg-emerald-50 text-emerald-600"
                        : ev.status === "error"
                          ? "bg-red-50 text-red-500"
                          : "bg-brand-50 text-brand-600"
                    }`}
                  >
                    {ev.status === "done" ? "完成" : ev.status === "error" ? "异常" : "进行中"}
                  </span>
                </div>
                <p className="truncate text-[11px] text-slate-500">{ev.message}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
