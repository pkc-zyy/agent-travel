import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Stats, WebSearchItem } from "../types";

export default function ArchitecturePage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [kbQuery, setKbQuery] = useState("丽江 亲子 酒店");
  const [kbResult, setKbResult] = useState<{ results: Array<{ id: string; text: string; meta: Record<string, unknown>; score: number }>; backend: string; embedding_mode: string } | null>(null);
  const [kbLoading, setKbLoading] = useState(false);
  const [webQuery, setWebQuery] = useState("丽江 玉龙雪山 门票 开放时间");
  const [webResult, setWebResult] = useState<{ results: WebSearchItem[] } | null>(null);
  const [webLoading, setWebLoading] = useState(false);

  useEffect(() => {
    api.stats().then(setStats).catch(() => setStats(null));
  }, []);

  const searchKb = async () => {
    if (!kbQuery.trim()) return;
    setKbLoading(true);
    try {
      setKbResult(await api.kbSearch(kbQuery.trim(), 4));
    } catch {
      setKbResult(null);
    } finally {
      setKbLoading(false);
    }
  };

  const searchWeb = async () => {
    if (!webQuery.trim()) return;
    setWebLoading(true);
    try {
      setWebResult(await api.webSearch(webQuery.trim(), 5));
    } catch {
      setWebResult(null);
    } finally {
      setWebLoading(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-5 sm:p-6">
      <h2 className="text-lg font-bold text-slate-900">系统架构</h2>
      <p className="mt-1 text-sm text-slate-500">多智能体协作 + RAG 混合检索 + MCP 工具协议 + 记忆与上下文管理</p>

      {/* 运行状态 */}
      {stats && (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
          <StatusChip label="LLM 模式" value={stats.llm_mode === "llm" ? "真实 LLM" : "离线模板"} color={stats.llm_mode === "llm" ? "emerald" : "amber"} />
          <StatusChip label="向量数据库" value={stats.rag.vector_backend} color="brand" />
          <StatusChip label="知识库文档" value={`${stats.rag.docs} 篇`} color="brand" />
          <StatusChip label="嵌入模式" value={stats.rag.embedding_mode === "api" ? "API 语义嵌入" : "本地哈希嵌入"} color="slate" />
          <StatusChip label="MCP 工具" value={`${stats.mcp_tools.length} 个`} color="brand" />
          <StatusChip label="支持城市" value={`${stats.cities.length} 个`} color="slate" />
        </div>
      )}

      {/* 多智能体协作图 */}
      <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-bold text-slate-800">🤖 多智能体协作架构</h3>
        <div className="mt-4 overflow-x-auto">
          <div className="min-w-[640px]">
            {/* 用户 */}
            <div className="flex justify-center">
              <div className="rounded-xl bg-slate-800 px-5 py-2.5 text-sm font-semibold text-white shadow">👤 用户</div>
            </div>
            <div className="my-1.5 text-center text-slate-300">↓ 需求 / 反馈</div>
            {/* 主管 */}
            <div className="flex justify-center">
              <div className="rounded-xl border-2 border-brand-500 bg-brand-50 px-5 py-2.5 text-sm font-bold text-brand-700 shadow-sm">🧠 主管协调器（Supervisor）</div>
            </div>
            <div className="my-1.5 text-center text-slate-300">意图识别 · 任务分发 · 上下文组装 · 结果整合</div>
            {/* 分叉到专家 */}
            <div className="mt-2 grid grid-cols-3 gap-3">
              {[
                { e: "🧭", n: "行程规划师", d: "解析需求 / 设计框架" },
                { e: "☀️", n: "天气顾问", d: "城市天气 / 出行建议" },
                { e: "🏨", n: "酒店专家", d: "预算 / 偏好筛住宿" },
                { e: "🏔️", n: "景点研究员", d: "兴趣匹配选景点" },
                { e: "🌐", n: "实时搜索员", d: "网页搜索最新信息" },
                { e: "💰", n: "预算会计师", d: "人均成本核算" },
                { e: "🕵️", n: "方案审查官", d: "质量门禁 / 迭代优化" },
              ].map((a) => (
                <div key={a.n} className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-center">
                  <div className="text-2xl">{a.e}</div>
                  <div className="mt-1 text-[13px] font-semibold text-slate-800">{a.n}</div>
                  <div className="mt-0.5 text-[11px] text-slate-500">{a.d}</div>
                </div>
              ))}
            </div>
            {/* MCP 层 */}
            <div className="mt-3 rounded-xl border border-dashed border-brand-300 bg-brand-50/40 px-4 py-2.5 text-center text-[13px] text-brand-700">
              🔌 MCP 协议：Agent → MCP Server（天气 / 酒店 / 景点 / 网页搜索 / 知识检索 / 反馈 / 记忆工具），同时开放标准端点 <code className="rounded bg-white px-1">/mcp</code>（SSE）
            </div>
            {/* 底层能力 */}
            <div className="mt-3 grid grid-cols-3 gap-3">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="text-[13px] font-semibold text-slate-800">🔍 RAG 混合检索</div>
                <div className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  向量（ChromaDB）+ BM25 → RRF 融合 → 城市感知重排
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="text-[13px] font-semibold text-slate-800">🌐 网页搜索</div>
                <div className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  Tavily / SerpAPI / DuckDuckGo / Bing 多 provider 降级，补充实时信息
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="text-[13px] font-semibold text-slate-800">🧠 记忆管理</div>
                <div className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  短期会话窗口+摘要 · 长期偏好/教训向量记忆 · 预算化上下文组装
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="text-[13px] font-semibold text-slate-800">⚡ 异步并发</div>
                <div className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  FastAPI 异步 · asyncio.gather 并行专家 · 缓存 · 后台学习任务
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* RAG 演示 */}
      <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-bold text-slate-800">🔍 RAG 混合检索演示</h3>
        <p className="mt-1 text-xs text-slate-500">向量 + BM25 双通道召回，RRF 融合排序，展示知识库检索能力</p>
        <div className="mt-3 flex gap-2">
          <input
            value={kbQuery}
            onChange={(e) => setKbQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && searchKb()}
            className="flex-1 rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            placeholder="输入检索内容，如：北京 亲子 必去 景点"
          />
          <button onClick={searchKb} disabled={kbLoading} className="rounded-xl bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
            {kbLoading ? "检索中…" : "检索"}
          </button>
        </div>
        {kbResult && (
          <div className="mt-3">
            <div className="text-[11px] text-slate-400">
              后端：{kbResult.backend} · 嵌入：{kbResult.embedding_mode} · 召回 {kbResult.results.length} 条
            </div>
            <div className="mt-2 space-y-2">
              {kbResult.results.map((r) => (
                <div key={r.id} className="rounded-xl border border-slate-100 bg-slate-50/60 p-3">
                  <div className="flex items-center justify-between">
                    <span className="rounded bg-white px-1.5 py-0.5 text-[11px] font-medium text-brand-600 border border-brand-100">
                      {String(r.meta.kind)} · {String(r.meta.city ?? r.meta.name ?? "")}
                    </span>
                    <span className="text-[11px] text-slate-400">融合分 {r.score.toFixed(3)}</span>
                  </div>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-slate-700">{r.text}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 网页搜索演示 */}
      <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-bold text-slate-800">🌐 网页搜索演示</h3>
        <p className="mt-1 text-xs text-slate-500">实时搜索互联网（Tavily / SerpAPI / DuckDuckGo / Bing 多 provider 降级），补充门票、开放时间、最新活动</p>
        <div className="mt-3 flex gap-2">
          <input
            value={webQuery}
            onChange={(e) => setWebQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && searchWeb()}
            className="flex-1 rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            placeholder="输入搜索内容，如：三亚 蜈支洲岛 潜水 价格"
          />
          <button onClick={searchWeb} disabled={webLoading} className="rounded-xl bg-emerald-600 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50">
            {webLoading ? "搜索中…" : "搜索"}
          </button>
        </div>
        {webResult && (
          <div className="mt-3 space-y-2">
            {webResult.results.length === 0 ? (
              <p className="text-xs text-slate-400">未获取到搜索结果（网络受限时可用本地「RAG 检索」替代）</p>
            ) : (
              webResult.results.map((r, i) => (
                <div key={i} className="rounded-xl border border-slate-100 bg-slate-50/60 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <a href={r.url} target="_blank" rel="noreferrer" className="min-w-0 truncate text-[13px] font-semibold text-brand-600 hover:underline">
                      {r.title}
                    </a>
                    <span className="shrink-0 rounded bg-white px-1.5 py-0.5 text-[11px] text-slate-400 border border-slate-100">{r.source}</span>
                  </div>
                  <p className="mt-1 text-[13px] leading-relaxed text-slate-600">{r.snippet}</p>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* 技术栈 */}
      <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="text-sm font-bold text-slate-800">🛠️ 技术栈</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {[
            "Python 3.13", "FastAPI", "SQLAlchemy 2 (async)", "SQLite + aiosqlite",
            "ChromaDB 向量库", "rank-bm25", "RRF 融合", "OpenAI 兼容 SDK",
            "MCP SDK (FastMCP + SSE)", "httpx 异步", "asyncio 并发",
            "DuckDuckGo/Bing 网页搜索", "Tavily/SerpAPI(可选)",
            "React 18", "TypeScript", "Vite", "Tailwind CSS 4",
          ].map((t) => (
            <span key={t} className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600">{t}</span>
          ))}
        </div>
        <div className="mt-4 grid gap-3 text-xs text-slate-500 sm:grid-cols-3">
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="font-semibold text-slate-700">📁 项目结构</div>
            <pre className="mt-1.5 overflow-x-auto text-[11px] leading-relaxed">{`backend/
  app/
    agents/     9 个智能体
    rag/        向量+BM25+融合
    mcp_server/ MCP 工具协议
    memory/     会话+长期记忆
    api/        REST + SSE
  data/knowledge/ 133 篇知识文档
frontend/
  src/pages/   7 个功能页面
  src/components/ 卡片组件`}</pre>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="font-semibold text-slate-700">💰 付费闭环</div>
            <div className="mt-1.5 leading-relaxed">
              规划方案 → 发起支付订单 → 线下转账 → 管理员<b>人工确认收款</b>（记录操作人）→ 方案解锁
            </div>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="font-semibold text-slate-700">💡 可扩展</div>
            <div className="mt-1.5 leading-relaxed">
              在 backend/.env 填入 LLM Key 即切换真实推理与语义嵌入；MCP 端点可被 Claude Desktop 等外部客户端接入；数据库可平滑迁移到 PostgreSQL
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusChip({ label, value, color }: { label: string; value: string; color: "brand" | "emerald" | "amber" | "slate" }) {
  const colors = {
    brand: "bg-brand-50 text-brand-700 border-brand-200",
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    slate: "bg-slate-50 text-slate-600 border-slate-200",
  };
  return (
    <div className={`rounded-xl border px-3 py-2.5 ${colors[color]}`}>
      <div className="text-[11px] opacity-70">{label}</div>
      <div className="mt-0.5 truncate text-[13px] font-semibold">{value}</div>
    </div>
  );
}
