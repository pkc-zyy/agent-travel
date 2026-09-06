import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { LlmSettings } from "../types";

const PROVIDERS = [
  { key: "aliyun", label: "阿里云百炼（通义千问）", base: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus", embedding: "text-embedding-v3" },
  { key: "deepseek", label: "DeepSeek", base: "https://api.deepseek.com/v1", model: "deepseek-chat", embedding: "" },
  { key: "openai", label: "OpenAI", base: "https://api.openai.com/v1", model: "gpt-4o-mini", embedding: "text-embedding-3-small" },
  { key: "custom", label: "自定义（OpenAI 兼容）", base: "", model: "", embedding: "" },
];

interface AmapStatus {
  api_key_masked: string;
  has_key: boolean;
  source: string;
  ready: boolean;
}

export default function SettingsPage() {
  const [current, setCurrent] = useState<LlmSettings | null>(null);
  const [provider, setProvider] = useState("deepseek");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("text-embedding-3-small");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // 高德地图
  const [amap, setAmap] = useState<AmapStatus | null>(null);
  const [amapKey, setAmapKey] = useState("");
  const [amapMsg, setAmapMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [amapSaving, setAmapSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await api.getLlmSettings();
      setCurrent(s);
      setProvider(s.provider === "offline" ? "deepseek" : s.provider);
      setBaseUrl(s.base_url);
      setModel(s.model);
      setEmbeddingModel(s.embedding_model || "text-embedding-3-small");
    } catch {
      /* 静默 */
    }
    try {
      setAmap(await api.getAmapSettings());
    } catch {
      /* 静默 */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onProviderChange = (p: string) => {
    setProvider(p);
    const def = PROVIDERS.find((x) => x.key === p);
    setBaseUrl(def?.base ?? "");
    setModel(def?.model ?? "");
    setEmbeddingModel(def?.embedding ?? "");
  };

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const s = await api.saveLlmSettings({ provider, api_key: apiKey.trim(), base_url: baseUrl.trim(), model: model.trim(), embedding_model: embeddingModel.trim() });
      setCurrent(s);
      setApiKey("");
      setMsg({ ok: true, text: "✅ 配置已保存并即时生效（无需重启）。若嵌入模型变化，知识库索引将自动重建。" });
    } catch (e) {
      setMsg({ ok: false, text: `保存失败：${(e as Error).message}` });
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setMsg(null);
    try {
      const r = await api.testLlm({ provider, api_key: apiKey.trim(), base_url: baseUrl.trim(), model: model.trim() });
      setMsg({ ok: r.ok, text: r.ok ? `✅ ${r.message}` : `❌ ${r.message}` });
    } catch (e) {
      setMsg({ ok: false, text: `测试失败：${(e as Error).message}` });
    } finally {
      setTesting(false);
    }
  };

  const clear = async () => {
    setSaving(true);
    setMsg(null);
    try {
      const s = await api.saveLlmSettings({ provider: "custom", api_key: "", base_url: "", model: "", embedding_model: "" });
      setCurrent(s);
      setApiKey("");
      setMsg({ ok: true, text: "✅ 已清除运行时配置，回退为离线模式（或 .env 配置）" });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };

  const saveAmap = async (key: string, action: "save" | "test") => {
    setAmapSaving(true);
    setAmapMsg(null);
    try {
      if (action === "test") {
        const r = await api.testAmap(key);
        setAmapMsg({ ok: r.ok, text: (r.ok ? "✅ " : "❌ ") + r.message });
        if (r.ok) setAmap(await api.getAmapSettings());
      } else {
        const s = await api.saveAmapSettings(key);
        setAmap(s);
        setAmapKey("");
        setAmapMsg({
          ok: true,
          text: s.has_key ? "✅ 高德 Key 已保存并即时生效，酒店查询将优先使用高德地图真实数据" : "✅ 已清除高德 Key，酒店查询回退本地知识库",
        });
      }
    } catch (e) {
      setAmapMsg({ ok: false, text: (e as Error).message });
    } finally {
      setAmapSaving(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-5 sm:p-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-indigo-600 text-xl text-white shadow">
          ⚙️
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-900">设置</h2>
          <p className="text-sm text-slate-500">接入您自己的 LLM API，让智能体升级为真实大模型推理</p>
        </div>
      </div>

      {/* 当前状态 */}
      {current && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <span
            className={`flex h-2.5 w-2.5 rounded-full ${current.ready ? "bg-emerald-500" : "bg-slate-300"}`}
          />
          <span className="text-sm font-semibold text-slate-800">
            {current.ready ? "已启用 LLM" : "离线模式（未配置 API Key）"}
          </span>
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-500">
            来源：{current.source === "runtime" ? "界面配置" : current.source === "env" ? "环境变量(.env)" : "无"}
          </span>
          {current.has_key && (
            <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs text-brand-600">Key：{current.api_key_masked}</span>
          )}
          {current.model && (
            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-500">模型：{current.model}</span>
          )}
        </div>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        {/* 配置表单 */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-bold text-slate-800">🔑 LLM API 配置</h3>

          <label className="mt-4 block text-xs font-medium text-slate-500">服务商</label>
          <select
            value={provider}
            onChange={(e) => onProviderChange(e.target.value)}
            className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm outline-none focus:border-brand-400"
          >
            {PROVIDERS.map((p) => (
              <option key={p.key} value={p.key}>{p.label}</option>
            ))}
          </select>

          <label className="mt-4 block text-xs font-medium text-slate-500">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={current?.has_key ? `已保存（${current.api_key_masked}），留空则保持不变` : "sk-..."}
            className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          />

          <label className="mt-4 block text-xs font-medium text-slate-500">Base URL（OpenAI 兼容网关）</label>
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.deepseek.com/v1"
            className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-brand-400"
          />

          <label className="mt-4 block text-xs font-medium text-slate-500">模型</label>
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="deepseek-chat"
            className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-brand-400"
          />

          <label className="mt-4 block text-xs font-medium text-slate-500">Embedding 模型（用于 RAG 语义检索）</label>
          <input
            value={embeddingModel}
            onChange={(e) => setEmbeddingModel(e.target.value)}
            placeholder="text-embedding-3-small"
            className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-brand-400"
          />
          <p className="mt-1 text-[11px] text-slate-400">
            复用同一个 API Key 调用嵌入接口；留空或用不支持的模型时自动回退本地哈希嵌入。切换模型会触发向量索引自动重建。
          </p>

          {msg && (
            <div className={`mt-4 rounded-xl px-4 py-2.5 text-sm ${msg.ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
              {msg.text}
            </div>
          )}

          <div className="mt-4 flex gap-2">
            <button
              onClick={save}
              disabled={saving}
              className="flex-1 rounded-xl bg-brand-600 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
            >
              {saving ? "保存中…" : "保存并启用"}
            </button>
            <button
              onClick={test}
              disabled={testing}
              className="rounded-xl border border-brand-200 px-4 py-2.5 text-sm font-medium text-brand-600 transition hover:bg-brand-50 disabled:opacity-50"
            >
              {testing ? "测试中…" : "测试连接"}
            </button>
          </div>
          <button onClick={clear} disabled={saving} className="mt-2 w-full rounded-xl border border-slate-200 py-2 text-xs text-slate-500 hover:bg-slate-50">
            清除配置（回退离线模式）
          </button>
        </div>

        {/* 说明 */}
        <div className="space-y-4">
          {/* 高德地图 */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-800">🗺️ 高德地图 API（酒店真实数据）</h3>
              <span
                className={`flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                  amap?.ready ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-500"
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${amap?.ready ? "bg-emerald-500" : "bg-slate-300"}`} />
                {amap?.ready ? "已启用 · 高德真实数据" : "未配置 · 默认本地知识库"}
              </span>
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
              配置后酒店查询优先使用高德地图真实 POI（含地址、人均价、精确坐标，路线规划更准）；
              未配置时回退内置知识库数据。<b>个人开发者免费</b>，
              <a href="https://console.amap.com/dev/key/app" target="_blank" rel="noreferrer" className="text-brand-600 hover:underline">申请「Web服务」Key →</a>
            </p>
            {amap?.has_key && (
              <p className="mt-2 text-xs text-slate-500">
                当前 Key：<code className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px]">{amap.api_key_masked}</code>
                （来源：{amap.source === "runtime" ? "界面配置" : "环境变量(.env)"}）
              </p>
            )}
            <label className="mt-3 block text-xs font-medium text-slate-500">API Key</label>
            <input
              type="password"
              value={amapKey}
              onChange={(e) => setAmapKey(e.target.value)}
              placeholder={
                amap?.has_key
                  ? `已保存（${amap.api_key_masked}），输入新 Key 可替换`
                  : "您未配置高德地图，默认本地知识库"
              }
              className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            />
            {!amap?.has_key && (
              <p className="mt-1.5 text-[11px] text-violet-500">
                💡 粘贴 Key 后点击「保存并启用」，酒店与长尾城市景点即切换为高德真实数据
              </p>
            )}
            {amapMsg && (
              <div className={`mt-2.5 rounded-xl px-3.5 py-2 text-xs ${amapMsg.ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
                {amapMsg.text}
              </div>
            )}
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => saveAmap(amapKey.trim(), "save")}
                disabled={amapSaving || !amapKey.trim()}
                className="flex-1 rounded-xl bg-brand-600 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
              >
                {amapSaving ? "处理中…" : "保存并启用"}
              </button>
              <button
                onClick={() => saveAmap(amapKey.trim(), "test")}
                disabled={amapSaving || !amapKey.trim()}
                className="rounded-xl border border-brand-200 px-4 py-2 text-sm font-medium text-brand-600 transition hover:bg-brand-50 disabled:opacity-50"
              >
                测试连接
              </button>
              <button
                onClick={() => saveAmap("", "save")}
                disabled={amapSaving || !amap?.has_key}
                className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-500 transition hover:bg-slate-50 disabled:opacity-50"
              >
                清除
              </button>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800">💡 如何使用</h3>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-[13px] leading-relaxed text-slate-600">
              <li>选择服务商（DeepSeek / OpenAI / 自定义 OpenAI 兼容网关）</li>
              <li>填入 API Key、Base URL 与模型名</li>
              <li>点击「测试连接」验证连通性</li>
              <li>点击「保存并启用」，配置<b>即时生效</b>，无需重启</li>
            </ol>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800">🔒 关于安全</h3>
            <p className="mt-2 text-[13px] leading-relaxed text-slate-600">
              API Key 仅保存在本机后端（<code className="rounded bg-slate-100 px-1">data/runtime_config.json</code>），
              不会上传到第三方，仅用于向您指定的 Base URL 发起请求。Key 展示时已脱敏。
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800">🧭 说明</h3>
            <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-slate-600">
              <li>配置后：智能体对话、需求解析、反馈学习改用真实 LLM 推理</li>
              <li><b>RAG 语义嵌入</b>：有 Key 时用 API 嵌入（Embedding 模型），无 Key 时自动回退本地哈希嵌入</li>
              <li>切换 Key / Embedding 模型会触发向量索引<b>自动重建</b>，无需手动干预</li>
              <li>离线模式（未配置 Key）下系统用内置规则引擎，功能仍完整可用</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
