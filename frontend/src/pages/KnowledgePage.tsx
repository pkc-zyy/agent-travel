import { useCallback, useEffect, useRef, useState } from "react";
import { api, getUserId } from "../api/client";
import type { KnowledgeDoc } from "../types";

const userId = getUserId();

export default function KnowledgePage() {
  const [docs, setDocs] = useState<KnowledgeDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [notice, setNotice] = useState("");

  // 文件上传
  const [fileTitle, setFileTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 文本粘贴
  const [textTitle, setTextTitle] = useState("");
  const [text, setText] = useState("");
  const [ingesting, setIngesting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setDocs(await api.listKnowledgeDocs(userId));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const doUpload = async () => {
    if (!file) return;
    setUploading(true);
    setErr("");
    setNotice("");
    try {
      await api.uploadKnowledgeFile(file, fileTitle, userId);
      setNotice(`✅ 已入库「${file.name}」，已进入 RAG 检索`);
      setFile(null);
      setFileTitle("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      refresh();
    } catch (e) {
      setErr(`上传失败：${(e as Error).message}`);
    } finally {
      setUploading(false);
    }
  };

  const doIngest = async () => {
    if (!text.trim()) return;
    setIngesting(true);
    setErr("");
    setNotice("");
    try {
      await api.ingestKnowledgeText(textTitle, text, userId);
      setNotice("✅ 文本已入库，已进入 RAG 检索");
      setText("");
      setTextTitle("");
      refresh();
    } catch (e) {
      setErr(`入库失败：${(e as Error).message}`);
    } finally {
      setIngesting(false);
    }
  };

  const doDelete = async (id: number) => {
    if (!confirm("确定从知识库移除该资料吗？移除后不再参与检索。")) return;
    try {
      await api.deleteKnowledgeDoc(id);
      refresh();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-5 sm:p-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 text-xl text-white shadow">
          📚
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-900">知识库</h2>
          <p className="text-sm text-slate-500">上传您自己的资料，Agent 回答时将基于这些资料进行 RAG 检索</p>
        </div>
      </div>

      {(err || notice) && (
        <div className={`mt-4 rounded-xl px-4 py-2.5 text-sm ${err ? "bg-red-50 text-red-600" : "bg-emerald-50 text-emerald-700"}`}>
          {err || notice}
        </div>
      )}

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        {/* 上传文件 */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-bold text-slate-800">📄 上传文件</h3>
          <p className="mt-1 text-xs text-slate-400">支持 .txt / .md / .csv / .json / .log（≤5MB），自动分块并建立向量 + BM25 索引</p>
          <label
            htmlFor="kb-file"
            className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50/60 px-4 py-6 text-center transition hover:border-emerald-300 hover:bg-emerald-50/40"
          >
            <span className="text-2xl">📎</span>
            <span className="mt-1.5 text-sm text-slate-600">
              {file ? `已选择：${file.name}` : "点击选择文件，或拖拽到此处"}
            </span>
          </label>
          <input
            id="kb-file"
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.markdown,.csv,.json,.log"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <input
            value={fileTitle}
            onChange={(e) => setFileTitle(e.target.value)}
            placeholder="资料标题（可选，默认用文件名）"
            className="mt-3 w-full rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-emerald-400"
          />
          <button
            onClick={doUpload}
            disabled={!file || uploading}
            className="mt-3 w-full rounded-xl bg-emerald-600 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
          >
            {uploading ? "入库中…" : "上传并入库"}
          </button>
        </div>

        {/* 粘贴文本 */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-bold text-slate-800">✍️ 粘贴文本</h3>
          <p className="mt-1 text-xs text-slate-400">直接把攻略、行程单、公司资料等文本粘贴进来</p>
          <input
            value={textTitle}
            onChange={(e) => setTextTitle(e.target.value)}
            placeholder="标题（可选）"
            className="mt-3 w-full rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-emerald-400"
          />
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={7}
            placeholder="在此粘贴文本内容…"
            className="mt-2 w-full resize-none rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100"
          />
          <button
            onClick={doIngest}
            disabled={!text.trim() || ingesting}
            className="mt-3 w-full rounded-xl bg-emerald-600 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
          >
            {ingesting ? "入库中…" : "入库"}
          </button>
        </div>
      </div>

      {/* 资料列表 */}
      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800">
          🗂️ 已入库资料
          <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-600">{docs.length}</span>
        </h3>
        {loading ? (
          <p className="mt-3 text-sm text-slate-400">加载中…</p>
        ) : docs.length === 0 ? (
          <p className="mt-3 text-xs text-slate-400">
            还没有自定义资料。上传一份文档后，可到「系统架构」页的 RAG 检索演示，或直接向智能体提问验证检索效果。
          </p>
        ) : (
          <div className="mt-3 space-y-2">
            {docs.map((d) => (
              <div key={d.id} className="flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50/60 px-4 py-3">
                <span className="text-xl">📄</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-slate-800">{d.title}</div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-slate-400">
                    <span className="truncate">{d.filename}</span>
                    <span>{d.char_count} 字</span>
                    <span>{d.chunk_count} 分块</span>
                    <span>{new Date(d.created_at).toLocaleString("zh-CN")}</span>
                  </div>
                </div>
                <button
                  onClick={() => doDelete(d.id)}
                  className="shrink-0 rounded-lg border border-red-200 px-2.5 py-1 text-xs text-red-500 hover:bg-red-50"
                >
                  删除
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
