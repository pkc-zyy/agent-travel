import { useEffect, useRef, useState } from "react";
import { api, getSessionId, getUserId } from "../api/client";
import type { AgentEvent, ChatResult, Order, OrderOffer } from "../types";
import type { PageKey } from "../components/Layout";
import AgentTrace from "../components/AgentTrace";
import Markdown from "../components/Markdown";
import PlanView from "../components/PlanView";

type OrderState = "idle" | "creating" | "created" | "declined" | "error";

interface Message {
  role: "user" | "assistant";
  content: string;
  intent?: string;
  data?: ChatResult["data"];
  error?: boolean;
  orderOffer?: OrderOffer | null;
  orderState?: OrderState;
  order?: Order | null;
  orderMsg?: string;
}

const SUGGESTIONS = [
  "帮我规划云南昆明-大理-丽江 5 日游，人均 4000",
  "推荐丽江适合情侣的酒店",
  "北京必去的景点有哪些",
  "三亚周末天气怎么样",
  "上次行程太赶了",
];

const sessionId = getSessionId();
const userId = getUserId();

export default function ChatPage({ onNavigate }: { onNavigate: (p: PageKey) => void }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [trace, setTrace] = useState<AgentEvent[]>([]);
  const [traceOpen, setTraceOpen] = useState(false);
  const [errMsg, setErrMsg] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, trace]);

  const send = async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || busy) return;
    setInput("");
    setErrMsg("");
    setTrace([]);
    setTraceOpen(true);
    setBusy(true);
    setMessages((m) => [...m, { role: "user", content }]);

    const assistantId = `a_${Date.now()}`;
    setMessages((m) => [...m, { role: "assistant", content: "", intent: "pending" }]);

    const abort = new AbortController();
    abortRef.current = abort;
    let finalResult: ChatResult | null = null;

    try {
      await api.chatStream(content, sessionId, userId, (ev) => {
        const type = ev.type as string;
        if (type === "agent") {
          setTrace((t) => [...t, ev as unknown as AgentEvent]);
        } else if (type === "result") {
          finalResult = ev as unknown as ChatResult;
        } else if (type === "error") {
          setErrMsg(String(ev.message ?? "未知错误"));
        }
      }, abort.signal);

      if (!finalResult) {
        throw new Error("未收到智能体结果");
      }
      setMessages((m) =>
        m.map((msg) =>
          msg.role === "assistant" && msg.intent === "pending"
            ? {
                ...msg,
                content: finalResult!.reply,
                intent: finalResult!.intent,
                data: finalResult!.data,
                orderOffer: finalResult!.data?.order_offer ?? null,
                orderState: finalResult!.data?.order_offer ? "idle" : undefined,
              }
            : msg
        )
      );
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setErrMsg(`请求失败：${(e as Error).message}`);
      setMessages((m) =>
        m.map((msg) =>
          msg.role === "assistant" && msg.intent === "pending"
            ? { ...msg, content: "⚠️ 请求失败，请稍后重试。", intent: "error", error: true }
            : msg
        )
      );
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  const stop = () => abortRef.current?.abort();

  const updateMessage = (index: number, patch: Partial<Message>) => {
    setMessages((m) => m.map((msg, i) => (i === index ? { ...msg, ...patch } : msg)));
  };

  /** 规划完成后客户确认下单 */
  const placeOrder = async (index: number, offer: OrderOffer) => {
    updateMessage(index, { orderState: "creating", orderMsg: "" });
    try {
      const order = await api.createOrder({ user_id: userId, trip_id: offer.trip_id });
      updateMessage(index, { orderState: "created", order });
    } catch (e) {
      updateMessage(index, { orderState: "error", orderMsg: (e as Error).message });
    }
  };

  const declineOrder = (index: number) => {
    updateMessage(index, { orderState: "declined" });
  };

  return (
    <div className="flex h-full flex-col">
      {/* 顶部快捷入口 */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-white/70 px-4 py-2.5 backdrop-blur sm:px-8">
        <div className="text-sm font-semibold text-slate-700">💬 智能规划</div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigate("knowledge")}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition hover:border-emerald-300 hover:text-emerald-600"
          >
            📚 上传资料
          </button>
          <button
            onClick={() => onNavigate("settings")}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition hover:border-brand-300 hover:text-brand-600"
          >
            ⚙️ LLM 设置
          </button>
        </div>
      </div>

      {/* 消息区 */}
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-8">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center pb-10">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-indigo-600 text-3xl shadow-lg shadow-brand-200">
              ✈️
            </div>
            <h2 className="mt-4 text-xl font-bold text-slate-900">旅行星球</h2>
            <p className="mt-1.5 max-w-md text-center text-sm text-slate-500">
              多智能体协作的旅行规划平台 —— 路线规划、酒店推荐、景点攻略、天气查询、反馈学习，一站式搞定
            </p>
            <div className="mt-6 flex max-w-xl flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-[13px] text-slate-600 shadow-sm transition hover:border-brand-300 hover:text-brand-600"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`animate-fade-in-up flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            {msg.role === "assistant" && (
              <div className="mr-2.5 mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-indigo-600 text-base text-white shadow">
                ✈️
              </div>
            )}
            <div
              className={`rounded-2xl px-4 py-3 shadow-sm ${
                msg.role === "user"
                  ? "max-w-[85%] rounded-br-md border border-slate-200 bg-white text-slate-900 sm:max-w-[75%]"
                  : msg.intent === "plan"
                    ? "max-w-full rounded-bl-md border border-slate-200 bg-white"
                    : "max-w-[85%] rounded-bl-md border border-slate-200 bg-white sm:max-w-[75%]"
              }`}
            >
              {msg.intent === "pending" ? (
                <div className="flex items-center gap-2 py-1 text-sm text-slate-400">
                  <span className="flex gap-1">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-300" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-300 [animation-delay:0.15s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-300 [animation-delay:0.3s]" />
                  </span>
                  智能体团队协作中…
                </div>
              ) : msg.intent === "plan" && msg.data?.plan ? (
                <div>
                  <PlanView plan={msg.data.plan} />
                  {msg.orderOffer && (
                    <OrderOfferCard
                      offer={msg.orderOffer}
                      state={msg.orderState ?? "idle"}
                      order={msg.order ?? null}
                      errorMsg={msg.orderMsg ?? ""}
                      onAccept={() => placeOrder(i, msg.orderOffer!)}
                      onDecline={() => declineOrder(i)}
                      onNavigate={onNavigate}
                    />
                  )}
                </div>
              ) : (
                <Markdown content={msg.content} />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* 智能体协作过程 */}
      {trace.length > 0 && (
        <div className="px-4 sm:px-8">
          <AgentTrace events={trace} open={traceOpen} onToggle={() => setTraceOpen((v) => !v)} />
        </div>
      )}

      {/* 输入区 */}
      <div className="border-t border-slate-200 bg-white/80 px-4 py-3 backdrop-blur sm:px-8">
        {errMsg && <div className="mb-2 text-xs text-red-500">⚠️ {errMsg}</div>}
        <div className="mx-auto flex max-w-4xl items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder="描述您的旅行需求，例如：帮我规划成都-重庆 4 日游…"
            className="max-h-32 flex-1 resize-none rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          />
          {busy ? (
            <button
              onClick={stop}
              className="rounded-xl bg-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-300"
            >
              停止
            </button>
          ) : (
            <button
              onClick={() => send()}
              disabled={!input.trim()}
              className="rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              发送
            </button>
          )}
        </div>
        <p className="mx-auto mt-1.5 max-w-4xl text-center text-[11px] text-slate-400">
          支持：行程规划 · 酒店 · 景点 · 天气 · 反馈学习 · RAG 知识检索 · 长期记忆
        </p>
      </div>
    </div>
  );
}

/** 规划完成后的下单确认卡片：规划 → 主动询问 → 确认后生成订单 */
function OrderOfferCard({
  offer,
  state,
  order,
  errorMsg,
  onAccept,
  onDecline,
  onNavigate,
}: {
  offer: OrderOffer;
  state: OrderState;
  order: Order | null;
  errorMsg: string;
  onAccept: () => void;
  onDecline: () => void;
  onNavigate: (p: PageKey) => void;
}) {
  return (
    <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-bold text-slate-800">🧾 方案满意的话，是否为本次行程下单？</div>
        <div className="rounded-full bg-white px-3 py-1 text-sm font-bold text-brand-600 shadow-sm">
          约 ¥{offer.amount} / 人
        </div>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        行程 #{offer.trip_id} · 线下转账 + 人工确认到账 · 未消费前可取消
      </p>

      {state === "idle" && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={onAccept}
            className="rounded-xl bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
          >
            🧾 立即下单
          </button>
          <button
            onClick={onDecline}
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm text-slate-600 transition hover:bg-slate-50"
          >
            暂不需要
          </button>
        </div>
      )}

      {state === "creating" && <div className="mt-3 text-sm text-slate-500">订单生成中…</div>}

      {state === "created" && order && (
        <div className="mt-3 space-y-2">
          <div className="text-sm font-semibold text-emerald-700">
            ✅ 订单 TRAVEL-{String(order.id).padStart(6, "0")} 已生成（¥{order.amount}）
          </div>
          <pre className="whitespace-pre-wrap rounded-xl bg-white p-3 text-xs leading-relaxed text-slate-600">
            {order.payment_note}
          </pre>
          <button
            onClick={() => onNavigate("orders")}
            className="text-xs font-medium text-brand-600 hover:underline"
          >
            前往订单中心查看 →
          </button>
        </div>
      )}

      {state === "declined" && (
        <p className="mt-3 text-xs text-slate-500">
          好的，方案已保存至「我的行程」，随时可以在订单中心下单，或继续告诉我要调整的地方。
        </p>
      )}

      {state === "error" && (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-red-600">❌ 下单失败：{errorMsg}</p>
          <button onClick={onAccept} className="text-xs font-medium text-brand-600 hover:underline">
            重试
          </button>
        </div>
      )}
    </div>
  );
}
