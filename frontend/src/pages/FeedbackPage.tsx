import { useCallback, useEffect, useState } from "react";
import { api, getUserId } from "../api/client";
import type { FeedbackItem, MemoryItem, TripItem } from "../types";

const userId = getUserId();

const TAG_OPTIONS = ["酒店太贵", "路线太赶", "景点一般", "交通不便", "天气影响", "美食满意", "排队太久", "性价比高"];

export default function FeedbackPage() {
  const [trips, setTrips] = useState<TripItem[]>([]);
  const [tripId, setTripId] = useState<number | "">("");
  const [rating, setRating] = useState(5);
  const [hoverRating, setHoverRating] = useState(0);
  const [comment, setComment] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState("");
  const [list, setList] = useState<FeedbackItem[]>([]);
  const [learned, setLearned] = useState<MemoryItem[]>([]);
  const [stats, setStats] = useState<{ count: number; avg_rating: number; distribution: Record<string, number> } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [fb, lessons, st, pl] = await Promise.all([
        api.listFeedback(userId),
        api.learnedLessons(userId),
        api.feedbackStats(userId),
        api.listPlans(userId),
      ]);
      setList(fb);
      setLearned(lessons);
      setStats(st);
      setTrips(pl);
    } catch {
      /* 静默 */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggleTag = (t: string) =>
    setTags((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));

  const submit = async () => {
    if (!comment.trim() && tags.length === 0) {
      alert("请填写评论或选择标签");
      return;
    }
    setSubmitting(true);
    setDone("");
    try {
      const res = await api.submitFeedback({
        user_id: userId,
        trip_id: tripId === "" ? null : Number(tripId),
        rating,
        comment: comment.trim(),
        tags,
      });
      setDone(`✅ 感谢反馈！反馈分析师已开始学习（${res.feedback.tags.length > 0 ? `标签：${res.feedback.tags.join("、")}` : "已记录"}）`);
      setComment("");
      setTags([]);
      setRating(5);
      setTripId("");
      // 稍后刷新（后台学习完成后可看到 lessons）
      setTimeout(refresh, 1500);
    } catch (e) {
      setDone(`❌ 提交失败：${(e as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-5 sm:p-6">
      <h2 className="text-lg font-bold text-slate-900">反馈中心</h2>
      <p className="mt-1 text-sm text-slate-500">您的每次反馈都会被「反馈分析师」学习，写入长期记忆，让下次规划更懂您 —— 形成 规划 → 体验 → 反馈 → 学习 的闭环</p>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        {/* 左侧：提交反馈 */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="text-sm font-bold text-slate-800">📝 提交反馈</h3>

          <div className="mt-4">
            <label className="text-xs font-medium text-slate-500">关联行程（可选）</label>
            <select
              value={tripId}
              onChange={(e) => setTripId(e.target.value === "" ? "" : Number(e.target.value))}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-brand-400"
            >
              <option value="">不关联具体行程</option>
              {trips.map((t) => (
                <option key={t.id} value={t.id}>{t.title}</option>
              ))}
            </select>
          </div>

          <div className="mt-4">
            <label className="text-xs font-medium text-slate-500">整体评分</label>
            <div className="mt-1.5 flex items-center gap-1 text-2xl">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  onMouseEnter={() => setHoverRating(n)}
                  onMouseLeave={() => setHoverRating(0)}
                  onClick={() => setRating(n)}
                  className="transition-transform hover:scale-110"
                >
                  <span className={n <= (hoverRating || rating) ? "" : "opacity-25 grayscale"}>⭐</span>
                </button>
              ))}
              <span className="ml-2 text-sm text-slate-500">{["很差", "较差", "一般", "满意", "非常满意"][rating - 1]}</span>
            </div>
          </div>

          <div className="mt-4">
            <label className="text-xs font-medium text-slate-500">标签（可多选）</label>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {TAG_OPTIONS.map((t) => (
                <button
                  key={t}
                  onClick={() => toggleTag(t)}
                  className={`rounded-full px-3 py-1 text-xs transition ${
                    tags.includes(t)
                      ? "bg-brand-600 text-white shadow-sm"
                      : "border border-slate-200 bg-white text-slate-600 hover:border-brand-300"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4">
            <label className="text-xs font-medium text-slate-500">详细评论</label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              placeholder="例如：整体不错，但大理那晚酒店隔音不好，行程第三天有点赶…"
              className="mt-1 w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
            />
          </div>

          <button
            onClick={submit}
            disabled={submitting}
            className="mt-4 w-full rounded-xl bg-brand-600 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
          >
            {submitting ? "提交中…" : "提交反馈"}
          </button>
          {done && <p className="mt-2 text-xs text-slate-600">{done}</p>}
        </div>

        {/* 右侧：学习成果 */}
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
              <div className="text-2xl font-bold text-brand-600">{stats?.count ?? 0}</div>
              <div className="mt-0.5 text-xs text-slate-500">累计反馈</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
              <div className="text-2xl font-bold text-amber-500">{stats?.avg_rating ? `★ ${stats.avg_rating}` : "—"}</div>
              <div className="mt-0.5 text-xs text-slate-500">平均评分</div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800">
              🧠 系统已学到的经验
              <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] text-brand-600">{learned.length}</span>
            </h3>
            {learned.length === 0 ? (
              <p className="mt-3 text-xs text-slate-400">暂无学习记录。提交一条低分反馈试试，系统会把改进经验写入长期记忆。</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {learned.map((m) => (
                  <li key={m.id} className="flex items-start gap-2 rounded-xl bg-emerald-50/60 px-3 py-2 text-[13px] text-emerald-800">
                    <span className="mt-0.5">✅</span>
                    <span>{m.content}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800">📜 反馈历史</h3>
            {list.length === 0 ? (
              <p className="mt-3 text-xs text-slate-400">还没有反馈记录。</p>
            ) : (
              <div className="mt-3 space-y-2">
                {list.map((f) => (
                  <div key={f.id} className="rounded-xl border border-slate-100 bg-slate-50/60 p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-amber-500">{"⭐".repeat(f.rating)}<span className="text-slate-300">{"⭐".repeat(5 - f.rating)}</span></span>
                      <span className="text-[11px] text-slate-400">{new Date(f.created_at).toLocaleString("zh-CN")}</span>
                    </div>
                    {f.comment && <p className="mt-1.5 text-[13px] text-slate-700">{f.comment}</p>}
                    {f.tags.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {f.tags.map((t) => (
                          <span key={t} className="rounded-md bg-white px-1.5 py-0.5 text-[11px] text-slate-500 border border-slate-200">{t}</span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
