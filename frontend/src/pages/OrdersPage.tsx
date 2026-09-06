import { useCallback, useEffect, useState } from "react";
import { api, getUserId } from "../api/client";
import type { Order, TripItem } from "../types";

const userId = getUserId();

const STATUS_MAP: Record<string, { label: string; cls: string; icon: string }> = {
  draft: { label: "未支付", cls: "bg-slate-100 text-slate-500", icon: "⏳" },
  pending_payment: { label: "待人工确认", cls: "bg-amber-50 text-amber-600", icon: "⏳" },
  paid: { label: "已支付", cls: "bg-emerald-50 text-emerald-600", icon: "✅" },
  cancelled: { label: "已取消", cls: "bg-slate-100 text-slate-400", icon: "✖️" },
};

export default function OrdersPage() {
  const [tab, setTab] = useState<"mine" | "admin">("mine");
  const [trips, setTrips] = useState<TripItem[]>([]);
  const [myOrders, setMyOrders] = useState<Order[]>([]);
  const [pendingOrders, setPendingOrders] = useState<Order[]>([]);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // 发起支付
  const [tripId, setTripId] = useState<number | "">("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("线下转账");
  const [creating, setCreating] = useState(false);

  // 人工确认
  const [operator, setOperator] = useState("");
  const [note, setNote] = useState("");
  const [acting, setActing] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [t, mine, pend] = await Promise.all([
        api.listPlans(userId),
        api.listOrders(userId),
        api.listPendingOrders(),
      ]);
      setTrips(t);
      setMyOrders(mine);
      setPendingOrders(pend);
    } catch {
      /* 静默 */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const createOrder = async () => {
    if (tripId === "") {
      setMsg({ ok: false, text: "请先选择要支付的行程" });
      return;
    }
    setCreating(true);
    setMsg(null);
    try {
      const order = await api.createOrder({
        user_id: userId,
        trip_id: Number(tripId),
        amount: amount.trim() ? Number(amount) : undefined,
        payment_method: method,
      });
      setMsg({ ok: true, text: `✅ 订单 TRAVEL-${String(order.id).padStart(6, "0")} 已生成，请按支付指引转账，等待人工确认` });
      setTripId("");
      setAmount("");
      refresh();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setCreating(false);
    }
  };

  const confirmOrder = async (order: Order) => {
    if (!operator.trim()) {
      setMsg({ ok: false, text: "请输入操作人姓名（人工确认必须记录经办人）" });
      return;
    }
    setActing(true);
    setMsg(null);
    try {
      await api.confirmOrder(order.id, operator.trim(), note.trim());
      setMsg({ ok: true, text: `✅ 订单 TRAVEL-${String(order.id).padStart(6, "0")} 已人工确认收款（操作人：${operator.trim()}）` });
      setOperator("");
      setNote("");
      refresh();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setActing(false);
    }
  };

  const cancelOrder = async (id: number) => {
    if (!confirm("确定取消该订单吗？")) return;
    await api.cancelOrder(id);
    refresh();
  };

  return (
    <div className="h-full overflow-y-auto p-5 sm:p-6">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 text-xl text-white shadow">💰</div>
        <div>
          <h2 className="text-lg font-bold text-slate-900">订单中心</h2>
          <p className="text-sm text-slate-500">规划好行程后付费下单，由工作人员<b>人工确认收款</b>后开通</p>
        </div>
      </div>

      {/* Tab */}
      <div className="mt-4 inline-flex rounded-xl border border-slate-200 bg-white p-1">
        <button
          onClick={() => setTab("mine")}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${tab === "mine" ? "bg-brand-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-50"}`}
        >
          🧾 我的订单
        </button>
        <button
          onClick={() => setTab("admin")}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${tab === "admin" ? "bg-brand-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-50"}`}
        >
          👨‍💼 人工收款 {pendingOrders.length > 0 && <span className="ml-1 rounded-full bg-red-500 px-1.5 text-[11px] text-white">{pendingOrders.length}</span>}
        </button>
      </div>

      {msg && (
        <div className={`mt-3 rounded-xl px-4 py-2.5 text-sm ${msg.ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>{msg.text}</div>
      )}

      {tab === "mine" ? (
        <div className="mt-4 grid gap-5 lg:grid-cols-2">
          {/* 发起支付 */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800">💳 发起支付</h3>
            <p className="mt-1 text-xs text-slate-400">选择已规划好的行程，生成支付订单（金额默认取方案预算）</p>
            <label className="mt-3 block text-xs font-medium text-slate-500">选择行程</label>
            <select
              value={tripId}
              onChange={(e) => setTripId(e.target.value === "" ? "" : Number(e.target.value))}
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm outline-none focus:border-brand-400"
            >
              <option value="">— 请选择行程 —</option>
              {trips.map((t) => (
                <option key={t.id} value={t.id} disabled={t.payment_status === "paid" || t.payment_status === "pending_payment"}>
                  {t.title}（{STATUS_MAP[t.payment_status]?.label ?? t.payment_status}）
                </option>
              ))}
            </select>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-500">金额（¥，留空自动）</label>
                <input
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  type="number"
                  min="0"
                  placeholder="自动取预算"
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2 text-sm outline-none focus:border-brand-400"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-500">支付方式</label>
                <select
                  value={method}
                  onChange={(e) => setMethod(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm outline-none focus:border-brand-400"
                >
                  {["线下转账", "对公转账", "微信/支付宝", "现金"].map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
            </div>
            <button
              onClick={createOrder}
              disabled={creating || tripId === ""}
              className="mt-4 w-full rounded-xl bg-brand-600 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700 disabled:opacity-50"
            >
              {creating ? "生成订单中…" : "生成支付订单"}
            </button>
          </div>

          {/* 我的订单 */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800">🧾 我的订单</h3>
            {myOrders.length === 0 ? (
              <p className="mt-3 text-xs text-slate-400">暂无订单。先在左侧发起支付。</p>
            ) : (
              <div className="mt-3 space-y-3">
                {myOrders.map((o) => (
                  <OrderCard key={o.id} order={o} />
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-4 space-y-5">
          {/* 待人工确认 */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800">⏳ 待人工确认收款 <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-600">{pendingOrders.length}</span></h3>
            <p className="mt-1 text-xs text-slate-400">客户已转账，需工作人员核对到账后<b>人工确认</b>（记录操作人）</p>
            {pendingOrders.length === 0 ? (
              <p className="mt-3 text-xs text-slate-400">暂无待确认订单。</p>
            ) : (
              <div className="mt-3 space-y-3">
                <div className="flex flex-wrap items-end gap-3 rounded-xl bg-brand-50/60 p-3">
                  <div className="min-w-48 flex-1">
                    <label className="block text-xs font-medium text-slate-500">操作人姓名（必填，用于审计）</label>
                    <input
                      value={operator}
                      onChange={(e) => setOperator(e.target.value)}
                      placeholder="例如：客服小王"
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm outline-none focus:border-brand-400"
                    />
                  </div>
                  <div className="min-w-48 flex-1">
                    <label className="block text-xs font-medium text-slate-500">备注（可选）</label>
                    <input
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="到账流水号等"
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm outline-none focus:border-brand-400"
                    />
                  </div>
                </div>
                {pendingOrders.map((o) => (
                  <div key={o.id} className="rounded-xl border border-amber-200 bg-amber-50/40 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-sm font-bold text-slate-800">TRAVEL-{String(o.id).padStart(6, "0")}</div>
                        <div className="mt-0.5 text-xs text-slate-500">用户 {o.user_id} · 行程 #{o.trip_id} · {o.payment_method}</div>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-bold text-brand-600">¥{o.amount}</div>
                      </div>
                    </div>
                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={() => confirmOrder(o)}
                        disabled={acting}
                        className="flex-1 rounded-lg bg-emerald-600 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
                      >
                        {acting ? "处理中…" : "✅ 确认收款"}
                      </button>
                      <button
                        onClick={() => cancelOrder(o.id)}
                        className="rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-500 hover:bg-white"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 已处理订单 */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-bold text-slate-800">📋 全部订单</h3>
            <div className="mt-3 space-y-2">
              {myOrders.length === 0 && <p className="text-xs text-slate-400">暂无订单记录。</p>}
              {myOrders.map((o) => (
                <OrderCard key={o.id} order={o} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function OrderCard({ order }: { order: Order }) {
  const s = STATUS_MAP[order.status] ?? { label: order.status, cls: "bg-slate-100 text-slate-500", icon: "" };
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50/60 p-3.5">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-bold text-slate-800">TRAVEL-{String(order.id).padStart(6, "0")}</span>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${s.cls}`}>{s.icon} {s.label}</span>
          </div>
          <div className="mt-0.5 text-xs text-slate-500">
            行程 #{order.trip_id} · {order.payment_method} · {new Date(order.created_at).toLocaleString("zh-CN")}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-base font-bold text-slate-800">¥{order.amount}</div>
          {order.status === "paid" && order.operator && (
            <div className="text-[11px] text-emerald-600">经办：{order.operator}</div>
          )}
        </div>
      </div>
      {(order.payment_note || order.status === "pending_payment") && (
        <button onClick={() => setOpen(!open)} className="mt-1.5 text-xs text-brand-600 hover:underline">
          {open ? "收起支付指引 ▲" : "查看支付指引 ▼"}
        </button>
      )}
      {open && order.payment_note && (
        <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-white p-3 text-xs leading-relaxed text-slate-600">{order.payment_note}</pre>
      )}
      {order.status === "paid" && order.paid_at && (
        <div className="mt-1.5 text-[11px] text-slate-400">支付确认时间：{new Date(order.paid_at).toLocaleString("zh-CN")}</div>
      )}
    </div>
  );
}
