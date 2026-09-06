/** 与后端 API 对齐的类型定义 */

export interface AgentEvent {
  type: "agent";
  agent: string;
  name: string;
  emoji: string;
  role: string;
  status: "running" | "done" | "error";
  message: string;
  data?: Record<string, unknown>;
}

export interface WeatherInfo {
  city: string;
  date: string;
  condition: string;
  condition_en: string;
  t_max: number;
  t_min: number;
  humidity?: number;
  precip_prob: number;
  wind?: number;
  source: string;
  advice?: string;
  forecast?: Array<{ date: string; condition: string; t_max: number; t_min: number; precip_prob: number }>;
}

export interface GeoLocation {
  lat: number;
  lon: number;
}

export interface HotelInfo {
  name: string;
  city: string;
  price: number;
  rating: number;
  tags: string[];
  desc: string;
  address?: string;
  location?: GeoLocation | null;
  budget_level?: string;
  match_tags?: string[];
  score?: number;
  source?: "amap" | "local" | "llm";
}

export interface AttractionInfo {
  name: string;
  city: string;
  price: number;
  duration: string;
  tags: string[];
  desc: string;
  location?: GeoLocation | null;
  distance_km?: number;
  scheduled?: boolean;
  match_interests?: string[];
  source?: "amap" | "local" | "llm";
}

export interface ScheduleDay {
  day: number;
  city: string;
  title: string;
  weather?: WeatherInfo;
  attractions: AttractionInfo[];
  hotel?: HotelInfo;
  meals: string[];
  transport: string;
  route_summary?: string;
  activities: string[];
}

export interface HotelStrategy {
  strategy?: string;
  avg_km?: number | null;
  farthest_km?: number | null;
}

export interface OrderOffer {
  trip_id: number;
  amount: number;
  title: string;
}

export interface PlanData {
  title: string;
  summary: string;
  cities: string[];
  days: number;
  budget_range: string;
  travelers: string;
  start_date?: string;
  preferences: string[];
  schedule: ScheduleDay[];
  hotels: HotelInfo[];
  attractions: AttractionInfo[];
  weather: WeatherInfo[];
  web_results?: WebSearchGroup[];
  budget: { transport: number; hotel: number; food: number; tickets: number; total_per_person: number; currency?: string };
  tips: string[];
  agents: Array<{ name: string; emoji: string; role: string }>;
  review: { passed: boolean; score: number; issues: string[] };
  markdown: string;
  hotel_strategy?: Record<string, HotelStrategy>;
}

export interface ChatResult {
  reply: string;
  intent: string;
  data?: {
    plan?: PlanData;
    trip_id?: number;
    order_offer?: OrderOffer | null;
    spec?: Record<string, unknown>;
    weather?: WeatherInfo[];
    hotels?: HotelInfo[];
    attractions?: AttractionInfo[];
    knowledge?: string[];
    feedback?: { lessons: string[]; stored: number };
  } | null;
}

export interface TripItem {
  id: number;
  user_id: string;
  title: string;
  request: string;
  cities: string[];
  days: number;
  budget: string;
  rating: number;
  payment_status: "draft" | "pending_payment" | "paid";
  price: number;
  created_at: string;
}

export interface TripDetail extends TripItem {
  plan?: PlanData;
  markdown?: string;
}

export type OrderStatus = "pending_payment" | "paid" | "cancelled";

export interface Order {
  id: number;
  user_id: string;
  trip_id: number;
  amount: number;
  status: OrderStatus;
  payment_method: string;
  payment_note: string;
  operator: string;
  operator_note: string;
  paid_at: string | null;
  created_at: string;
}

export interface WebSearchItem {
  title: string;
  url: string;
  snippet: string;
  source: string;
}

export interface WebSearchGroup {
  query: string;
  city: string;
  results: WebSearchItem[];
}

export interface FeedbackItem {
  id: number;
  user_id: string;
  trip_id: number | null;
  rating: number;
  comment: string;
  tags: string[];
  lessons: string;
  created_at: string;
}

export interface MemoryItem {
  id: number;
  user_id: string;
  kind: "preference" | "fact" | "lesson";
  content: string;
  source: string;
  score: number;
  hit_count: number;
  created_at: string;
}

export interface Stats {
  app: string;
  llm_mode: string;
  rag: { ready: boolean; docs: number; vector_backend: string; vector_count: number; bm25_count: number; embedding_mode: string };
  mcp_tools: string[];
  agents: Array<{ name: string; emoji: string; role: string }>;
  cities: string[];
  db_counts: { trips: number; feedbacks: number; memories: number; knowledge_docs?: number };
}

export interface KnowledgeDoc {
  id: number;
  user_id: string;
  title: string;
  filename: string;
  char_count: number;
  chunk_count: number;
  created_at: string;
}

export interface LlmSettings {
  provider: string;
  api_key_masked: string;
  has_key: boolean;
  base_url: string;
  model: string;
  embedding_model: string;
  source: string;
  ready: boolean;
  mode: "llm" | "offline";
}

/* ---------- 运行监控 ---------- */
export type MonitorEventType = "api" | "tool" | "llm" | "agent" | "flow" | "error";

export interface MonitorEvent {
  id: number;
  ts: string;
  type: MonitorEventType;
  name: string;
  detail?: Record<string, unknown> | null;
  duration_ms?: number | null;
  status: "ok" | "error";
  session_id?: string;
}

export interface MonitorSummary {
  total: number;
  by_type: Record<string, { total: number; errors: number }>;
  by_name_top: Array<{ name: string; count: number }>;
  avg_ms: Record<string, number>;
  buffer_size: number;
  ts?: string;
}
