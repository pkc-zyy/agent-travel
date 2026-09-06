import type { ReactNode } from "react";

export type PageKey = "chat" | "plans" | "orders" | "feedback" | "knowledge" | "settings" | "monitor" | "architecture";

const NAV: Array<{ key: PageKey; icon: string; label: string; desc: string }> = [
  { key: "chat", icon: "💬", label: "智能规划", desc: "多 Agent 对话" },
  { key: "plans", icon: "🗺️", label: "我的行程", desc: "方案与详情" },
  { key: "orders", icon: "💰", label: "订单中心", desc: "付费与人工收款" },
  { key: "knowledge", icon: "📚", label: "知识库", desc: "上传资料入库" },
  { key: "feedback", icon: "📝", label: "反馈中心", desc: "反馈与学习" },
  { key: "monitor", icon: "📡", label: "运行监控", desc: "工具/LLM 调用监测" },
  { key: "settings", icon: "⚙️", label: "设置", desc: "接入 LLM / 高德 API" },
  { key: "architecture", icon: "🏗️", label: "系统架构", desc: "技术全景" },
];

export default function Layout({
  page,
  onNavigate,
  children,
}: {
  page: PageKey;
  onNavigate: (p: PageKey) => void;
  children: ReactNode;
}) {
  return (
    <div className="flex h-full">
      {/* 侧边栏 */}
      <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-indigo-600 text-lg text-white shadow-md shadow-brand-200">
            ✈️
          </div>
          <div>
            <div className="text-[15px] font-bold text-slate-900">旅行星球</div>
            <div className="text-[10px] text-slate-400">TravelAgent Platform</div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.map((item) => (
            <button
              key={item.key}
              onClick={() => onNavigate(item.key)}
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                page === item.key
                  ? "bg-brand-50 text-brand-700 ring-1 ring-brand-200"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              <span className="min-w-0">
                <span className="block text-[13px] font-semibold">{item.label}</span>
                <span className="block truncate text-[10px] opacity-60">{item.desc}</span>
              </span>
            </button>
          ))}
        </nav>
        <div className="border-t border-slate-100 px-5 py-4">
          <div className="text-[11px] leading-relaxed text-slate-400">
            🤖 8 个智能体协作
            <br />🔍 RAG + MCP + 记忆
          </div>
        </div>
      </aside>

      {/* 主内容 */}
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
