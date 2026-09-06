import type {
  ChatResult,
  FeedbackItem,
  KnowledgeDoc,
  LlmSettings,
  MemoryItem,
  MonitorEvent,
  MonitorSummary,
  Order,
  Stats,
  TripDetail,
  TripItem,
  WebSearchItem,
} from "../types";

const BASE = "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`请求失败 ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  /** 非流式对话 */
  chat: (message: string, sessionId: string, userId = "default") =>
    req<ChatResult>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId, user_id: userId, stream: false }),
    }),

  /** 流式对话：解析 SSE 事件，返回事件流 */
  chatStream: (
    message: string,
    sessionId: string,
    userId: string,
    onEvent: (ev: Record<string, unknown>) => void,
    signal?: AbortSignal
  ): Promise<void> =>
    fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId, user_id: userId, stream: true }),
      signal,
    }).then(async (res) => {
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE 事件以空行分隔
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const dataLine = part
            .split("\n")
            .find((l) => l.startsWith("data: "));
          if (!dataLine) continue;
          try {
            onEvent(JSON.parse(dataLine.slice(6)));
          } catch {
            /* 忽略无法解析的事件 */
          }
        }
      }
    }),

  // ---- 行程 ----
  listPlans: (userId = "default") => req<TripItem[]>(`/plans?user_id=${userId}`),
  getPlan: (id: number) => req<TripDetail>(`/plans/${id}`),
  updatePlan: (id: number, body: { title?: string; rating?: number }) =>
    req<TripItem>(`/plans/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deletePlan: (id: number) => req<{ ok: boolean }>(`/plans/${id}`, { method: "DELETE" }),

  // ---- 反馈 ----
  submitFeedback: (body: {
    user_id: string;
    trip_id?: number | null;
    rating: number;
    comment: string;
    tags: string[];
  }) =>
    req<{ feedback: FeedbackItem; status: string }>("/feedback", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listFeedback: (userId = "default") =>
    req<FeedbackItem[]>(`/feedback?user_id=${userId}`),
  learnedLessons: (userId = "default") =>
    req<MemoryItem[]>(`/feedback/learned?user_id=${userId}`),
  feedbackStats: (userId = "default") =>
    req<{ count: number; avg_rating: number; distribution: Record<string, number> }>(
      `/feedback/stats?user_id=${userId}`
    ),

  // ---- 记忆 ----
  listMemory: (userId = "default") => req<MemoryItem[]>(`/memory?user_id=${userId}`),
  addMemory: (body: { user_id: string; kind: string; content: string; source?: string }) =>
    req<{ ok: boolean; memory?: MemoryItem }>("/memory", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteMemory: (ids: number[]) =>
    req<{ ok: boolean }>("/memory", { method: "DELETE", body: JSON.stringify({ memory_ids: ids }) }),

  // ---- 系统 ----
  stats: () => req<Stats>("/stats"),
  kbSearch: (q: string, k = 3) =>
    req<{ query: string; backend: string; embedding_mode: string; results: Array<{ id: string; text: string; meta: Record<string, unknown>; score: number }> }>(
      `/kb/search?q=${encodeURIComponent(q)}&k=${k}`
    ),

  // ---- 知识库（用户资料上传，用于 RAG） ----
  listKnowledgeDocs: (userId = "default") =>
    req<KnowledgeDoc[]>(`/knowledge/documents?user_id=${userId}`),
  uploadKnowledgeFile: (file: File, title: string, userId = "default") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", title);
    fd.append("user_id", userId);
    return fetch(`${BASE}/knowledge/upload`, { method: "POST", body: fd }).then(async (res) => {
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text.slice(0, 200) || `HTTP ${res.status}`);
      }
      return res.json() as Promise<KnowledgeDoc>;
    });
  },
  ingestKnowledgeText: (title: string, text: string, userId = "default") =>
    req<KnowledgeDoc>("/knowledge/ingest", {
      method: "POST",
      body: JSON.stringify({ title, text, user_id: userId }),
    }),
  deleteKnowledgeDoc: (id: number) =>
    req<{ ok: boolean; removed_chunks: number }>(`/knowledge/documents/${id}`, { method: "DELETE" }),

  // ---- 设置（LLM API 接入） ----
  getLlmSettings: () => req<LlmSettings>("/settings/llm"),
  saveLlmSettings: (body: { provider: string; api_key: string; base_url: string; model: string; embedding_model: string }) =>
    req<LlmSettings>("/settings/llm", { method: "POST", body: JSON.stringify(body) }),
  testLlm: (body: { provider: string; api_key: string; base_url: string; model: string }) =>
    req<{ ok: boolean; message: string }>("/settings/llm/test", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // ---- 设置（高德地图 Key：真实酒店 POI） ----
  getAmapSettings: () =>
    req<{ api_key_masked: string; has_key: boolean; source: string; ready: boolean }>("/settings/amap"),
  saveAmapSettings: (api_key: string) =>
    req<{ api_key_masked: string; has_key: boolean; source: string; ready: boolean }>("/settings/amap", {
      method: "POST",
      body: JSON.stringify({ api_key }),
    }),
  testAmap: (api_key: string) =>
    req<{ ok: boolean; message: string }>("/settings/amap/test", {
      method: "POST",
      body: JSON.stringify({ api_key }),
    }),

  // ---- 运行监控（接口/工具/LLM/Agent 全链路） ----
  monitorEvents: (params: { limit?: number; type?: string; status?: string; q?: string } = {}) => {
    const sp = new URLSearchParams();
    if (params.limit) sp.set("limit", String(params.limit));
    if (params.type) sp.set("type", params.type);
    if (params.status) sp.set("status", params.status);
    if (params.q) sp.set("q", params.q);
    return req<{ events: MonitorEvent[] }>(`/monitor/events?${sp.toString()}`);
  },
  monitorSummary: () => req<MonitorSummary>("/monitor/summary"),
  /** SSE 实时事件流；onEvent 收到单条 MonitorEvent，返回取消函数 */
  monitorStream: (onEvent: (ev: MonitorEvent) => void, signal?: AbortSignal): Promise<void> =>
    fetch(`${BASE}/monitor/stream`, { signal }).then(async (res) => {
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const dataLine = part.split("\n").find((l) => l.startsWith("data: "));
          if (!dataLine) continue;
          try {
            const payload = JSON.parse(dataLine.slice(6));
            if (payload.type === "event" && payload.event) onEvent(payload.event as MonitorEvent);
          } catch {
            /* 忽略无法解析的事件 */
          }
        }
      }
    }),

  // ---- 订单 / 支付（人工确认） ----
  createOrder: (body: { user_id: string; trip_id: number; amount?: number; payment_method?: string }) =>
    req<Order>("/orders", { method: "POST", body: JSON.stringify(body) }),
  listOrders: (userId?: string) =>
    req<Order[]>(`/orders${userId ? `?user_id=${userId}` : ""}`),
  listPendingOrders: () => req<Order[]>("/orders/pending"),
  confirmOrder: (id: number, operator: string, note = "") =>
    req<Order>(`/orders/${id}/confirm`, { method: "POST", body: JSON.stringify({ operator, note }) }),
  cancelOrder: (id: number) =>
    req<Order>(`/orders/${id}/cancel`, { method: "POST" }),

  // ---- 网页搜索演示 ----
  webSearch: (q: string, k = 5) =>
    req<{ query: string; results: WebSearchItem[] }>(`/search?q=${encodeURIComponent(q)}&k=${k}`),
};

/** 生成会话 ID（持久于 localStorage） */
export function getSessionId(): string {
  let sid = localStorage.getItem("travel_session_id");
  if (!sid) {
    sid = `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    localStorage.setItem("travel_session_id", sid);
  }
  return sid;
}

export function getUserId(): string {
  let uid = localStorage.getItem("travel_user_id");
  if (!uid) {
    uid = `user_${Math.random().toString(36).slice(2, 8)}`;
    localStorage.setItem("travel_user_id", uid);
  }
  return uid;
}
