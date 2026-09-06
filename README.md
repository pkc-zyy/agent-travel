# 旅行星球 · TravelAgent — 多智能体旅行规划平台

一个 **前后端完整、开箱即用** 的旅行 Agent 项目：由 8 个智能体协作完成 **行程规划 / 酒店推荐 / 景点攻略 / 天气查询 / 用户反馈学习**，形成完整闭环。融合了当前主流的 Agent 技术：**RAG（向量数据库 + BM25 混合召回）、MCP 工具协议、记忆存储与上下文管理、后端异步并发**。

> ✅ 无需任何 API Key 即可完整运行（内置离线模板引擎 + 真实天气 API + 本地知识库）
> 🔑 配置 LLM Key 后自动升级为真实大模型推理与语义嵌入

---

## ✨ 功能一览

| 能力 | 说明 | 体验入口 |
| --- | --- | --- |
| 🗺️ 行程规划 | 解析目的地/天数/预算/偏好，多 Agent 并行产出每日行程（景点全程不重复、地理就近编排） | 智能规划 |
| 🏨 酒店推荐 | 优先高德地图真实 POI（地址/人均价/坐标），回退本地知识库；按「贴近景点群」自动选址 | 智能规划 |
| 🏔️ 景点推荐 | 按城市 + 兴趣标签匹配景点（含门票/时长/简介/坐标），每日动线与段间车程一目了然 | 智能规划 |
| ☀️ 天气查询 | Open-Meteo 实时天气（免费无 Key），失败自动降级模拟 | 智能规划 |
| 💰 规划后下单确认 | 方案生成后主动询问「是否下单」，页内一键生成支付订单 → 线下转账 → 人工确认收款 | 智能规划 / 订单中心 |
| 📝 用户反馈 | 评分 + 标签 + 评论 → 反馈分析师学习 → 写入长期记忆 | 反馈中心 |
| 🧠 记忆管理 | 会话级短期记忆（窗口+摘要） / 长期偏好教训记忆（向量召回） | 智能规划 / 反馈中心 |
| 🔍 RAG 检索 | 133 篇知识文档，向量 + BM25 双通道 → RRF 融合 → 城市感知重排 | 系统架构页可现场演示 |
| 🌐 网页搜索 | Tavily/SerpAPI/DuckDuckGo/Bing 多 provider 降级，补充门票/开放时间/实时活动 | 规划流程 + 架构页演示 |
| 📚 知识库资料 | 上传文件（txt/md 等）或粘贴文本 → 自动分块 → 实时入 RAG 双索引 | 知识库页 |
| ⚙️ LLM 接入 | 在界面填写自己的 API Key（DeepSeek/OpenAI/自定义网关），保存即生效 | 设置页 |
| 🗺️ 高德地图接入 | 界面填写高德「Web服务」Key（个人免费），酒店检索升级为真实 POI，即时生效 | 设置页 |
| 📡 运行监控 | 实时监测 HTTP 接口调用 / MCP 工具调用（含参数与输出摘要）/ LLM 调用 / Agent 事件，SSE 实时推送 | 运行监控页 |
| 🔌 MCP | Agent 经 MCP 协议调用工具；标准端点 `/mcp`（SSE）对外开放 | Claude Desktop 等可接入 |

## 🗺️ 支持城市

**精选 25 城（离线知识库，开箱即用）**：

| 区域 | 城市 |
| --- | --- |
| 云南线 | 昆明 · 大理 · 丽江 · 西双版纳 |
| 川渝湘 | 成都 · 重庆 · 长沙 · 张家界 |
| 华东线 | 上海 · 南京 · 苏州 · 杭州 |
| 华南线 | 广州 · 深圳 · 厦门 · 桂林 |
| 北方线 | 北京 · 西安 · 洛阳 · 青岛 · 大连 · 哈尔滨 |
| 西部线 | 武汉 · 拉萨 |

每城配备：城市指南（RAG）+ 6 个景点（含坐标/门票/时长）+ 4 家酒店（经济/舒适/豪华，含坐标）。

**长尾城市（需配置高德 Key）**：不在上表的城市（如景德镇、延安……），在「设置」页配置高德 Key 后同样可规划 —— 需求解析经高德地理编码验证城市、酒店与景点走高德真实 POI、天气自动定位城市中心；本地知识库城市则始终优先使用精选数据。

## 🏗️ 技术栈

**后端**：Python 3.13 · FastAPI · SQLAlchemy 2 (async) · SQLite/aiosqlite · ChromaDB 向量库 · rank-bm25 · MCP SDK (FastMCP + SSE) · OpenAI 兼容 SDK · httpx · asyncio

**前端**：React 18 · TypeScript · Vite · Tailwind CSS 4 · react-markdown

## 📁 项目结构

```
agent-travel/
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── agents/               # 9 个智能体（主管/规划/天气/酒店/景点/搜索员/预算/审查/反馈）
│   │   ├── rag/                  # embeddings / vector_store(Chroma) / bm25 / hybrid(RRF)
│   │   ├── mcp_server/           # MCP Server（FastMCP）+ MCP Client（in-memory transport）
│   │   ├── memory/               # 短期会话记忆 / 长期记忆 / 上下文管理器
│   │   ├── services/             # 天气 / 酒店 / 景点 / 网页搜索 / LLM(含离线回退) / 运行时配置
│   │   ├── api/                  # chat(SSE) / plans / orders / feedback / memory / knowledge / settings / stats / kb
│   │   ├── db/                   # SQLAlchemy 异步模型（行程/订单/反馈/记忆/知识库文档）
│   │   ├── main.py               # 应用装配 + MCP SSE 挂载
│   │   ├── config.py             # 环境配置
│   │   ├── prompts.py            # 集中管理所有提示词
│   │   └── models.py             # Pydantic 模型
│   ├── data/knowledge/           # 知识库语料（12 城市指南 / 72 景点 / 48 酒店 / 贴士）+ uploads/ 用户资料
│   └── scripts/                  # generate_knowledge / smoke_test
└── frontend/                     # React 前端（7 个页面）
    └── src/
        ├── pages/                # 智能规划 / 我的行程 / 订单中心 / 知识库 / 反馈中心 / 设置 / 系统架构
        ├── components/           # 卡片组件 / 行程可视化 / Agent 协作面板
        └── api/client.ts         # REST + SSE 客户端
```

## 🚀 快速开始

### 1. 后端

```bash
cd backend
pip install -r requirements.txt          # 安装依赖
python -m scripts.generate_knowledge     # 生成知识库语料（已生成可跳过）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> 首次启动会自动建表并构建 RAG 索引（向量 + BM25），约 1-3 秒。

### 2. 前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 （已配置代理到 :8000）
```

### 3. 一键启动（Windows）

```powershell
.\start.ps1        # 自动安装依赖 + 启动前后端
```

### 4. 冒烟测试

```bash
cd backend && python -m scripts.smoke_test
```

---

## 🧠 多智能体协作流程

```
用户需求
  │
  ▼
🧠 主管协调器（意图识别 / 上下文组装 / 任务分发）
  │
  ├── 🧭 行程规划师  解析需求 → 设计框架（城市×天数）
  │
  │   asyncio.gather 并行执行 ▼
  ├── ☀️ 天气顾问    （经 MCP）查询各城市天气
  ├── 🏨 酒店专家    （经 MCP）按预算/偏好推荐住宿
  ├── 🏔️ 景点研究员  （经 MCP）按兴趣推荐景点
  │
  ├── 💰 预算会计师  核算人均成本明细
  ├── 🕵️ 方案审查官  质量门禁（覆盖度/节奏/预算），未通过则迭代优化一轮
  │
  └── 📋 整合输出 → 结构化方案（日程/酒店/景点/天气/预算/贴士）→ 保存行程
```

## 🔍 RAG 混合检索设计

```
知识库（城市指南/景点/酒店/贴士，133 篇）
    │
    ├── 语义通道：Embedding（LLM API 或离线哈希）→ ChromaDB 向量库
    ├── 关键词通道：分词 → BM25 Okapi 索引
    │
    查询扩展（命中城市生成多路查询）
    │
    ▼
RRF 融合（Reciprocal Rank Fusion）→ 城市感知重排 → 注入上下文
```

## 🔌 MCP 设计

- **MCP Server**（`app/mcp_server/travel_mcp.py`）：FastMCP，暴露 `get_weather / search_hotels / search_attractions / get_city_info_tool / list_cities / kb_search / get_city_guide / web_search / save_feedback / get_user_preferences` 共 10 个工具。
- **MCP Client**（`app/mcp_server/client.py`）：Agent 经 MCP 协议（in-memory transport，真实 `initialize → tools/call` 握手）调用工具，协议层加锁保证并发安全。
- **对外开放**：FastAPI 挂载 `/mcp`（SSE 传输），任何标准 MCP 客户端（Claude Desktop / Cursor 等）可连接：
  ```
  mcp 服务器配置：transport=sse, url=http://localhost:8000/mcp
  ```
- **Pi 桥接（`pi-bridge/`）**：跨框架互操作示例——用 [Pi agent](https://github.com/earendil-works/pi)（`@earendil-works/pi-agent-core`，TypeScript）作为通用 Agent 运行时，经 MCP 协议驱动上述 10 个旅行工具，支持交互对话 / 单次提问 / 工具列表三种模式，详见 [`pi-bridge/README.md`](pi-bridge/README.md)。

## 🧠 记忆与上下文管理

| 层级 | 实现 | 策略 |
| --- | --- | --- |
| 短期会话记忆 | 内存滑动窗口 | 超窗自动压缩为摘要（LLM 摘要 / 抽取式兜底） |
| 长期记忆 | SQLite + 向量库双写 | 从对话/反馈抽取偏好、事实、教训；内容去重，命中强化（模拟间隔遗忘） |
| 上下文组装 | 预算化拼接 | 长期记忆 > RAG 知识 > 会话摘要 > 最近消息，按字符预算裁剪 |

## ⚡ 后端并发与异步

- FastAPI 全异步 + SQLAlchemy async engine（连接池）
- `asyncio.gather` 并行调度 天气/酒店/景点 三路专家
- 天气服务 TTL 缓存 + 请求级锁防击穿；Open-Meteo 失败自动降级
- 反馈学习、会话摘要、索引构建均为后台异步任务，不阻塞响应

## ⚙️ 配置 LLM（可选）

复制 `backend/.env.example` 为 `backend/.env`，填入任一 Key：

```ini
OPENAI_API_KEY=sk-...          # 或
DEEPSEEK_API_KEY=sk-...
# LLM_BASE_URL=...             # 自定义 OpenAI 兼容网关
# LLM_MODEL=deepseek-chat
```

不配置时系统自动运行在**离线模板模式**，功能完整可用；配置后自动切换真实 LLM 推理 + API 语义嵌入。

## 💬 提示词管理

所有提示词集中在 **`backend/app/prompts.py`** 统一维护（不在各模块散落），支持通过 `.env` 的 `PROMPT_*` 变量覆盖，改人设无需改代码：

| 变量 | 用途 |
| --- | --- |
| `PROMPT_SYSTEM` | 主管协调器主提示词（注入每次对话） |
| `PROMPT_SUMMARY` | 会话历史摘要 |
| `PROMPT_PLANNER_PARSE` | 行程需求 JSON 解析 |
| `PROMPT_FEEDBACK_LESSONS` | 反馈经验抽取 |
| `PROMPT_MEMORY_EXTRACT` | 长期记忆偏好抽取 |
| `PROMPT_MCP_INSTRUCTIONS` | MCP 服务器说明 |

```ini
# 示例：覆盖主提示词（多行用 \n）
# PROMPT_SYSTEM=你是资深旅行顾问，语气亲切，优先给出省钱建议...
```

> 离线模式（未配 Key）下部分提示词由内置规则模板代替，见 `backend/app/services/llm.py` 的 `FallbackEngine` 与 `backend/app/agents/orchestrator.py` 的意图回复。

## 📚 知识库资料 & ⚙️ LLM 接入（用户自助）

### 1. 知识库资料入口（用于 RAG）

在「**知识库**」页，用户可上传文件（.txt/.md/.csv/.json/.log，≤5MB）或直接粘贴文本。后端自动完成：

1. **分块**：按语义边界切分为 500 字左右的重叠块；
2. **双索引**：每块同时写入 ChromaDB 向量库 + BM25 索引；
3. **实时生效**：入库后立即参与 RAG 混合检索（可在「系统架构」页检索验证，或直接向智能体提问）；
4. **持久化**：资料落盘到 `data/knowledge/uploads/`，重启后自动重建索引；支持删除（同步移除索引）。

### 2. 接入自己的 LLM API

在「**设置**」页，用户可填写自己的 API Key（DeepSeek / OpenAI / 自定义 OpenAI 兼容网关）、Base URL 与模型，点击「测试连接」验证后「保存并启用」，**即时生效无需重启**。

- 配置优先级：界面运行时配置 > 环境变量(.env)；
- Key 仅存于本机 `data/runtime_config.json`，展示时脱敏；
- 清除配置即回退离线模式（或 .env）；
- 注意：RAG/记忆向量采用**语义嵌入（方案1）**——有 Key 时用 API Embedding（Embedding 模型），无 Key 或 API 不可用时自动回退本地哈希嵌入；切换 Key/模型会触发向量索引自动重建，无需重启。

## 🌐 网页搜索 & 💰 付费闭环

### 3. 网页搜索（实时信息）

新增「实时搜索员」智能体，在规划行程时并行搜索目的地最新信息（门票、开放时间、实时活动），结果注入方案与 Markdown。搜索采用**多 provider 降级**：

1. Tavily（配置 `TAVILY_API_KEY`）
2. SerpAPI（配置 `SERPAPI_KEY`）
3. DuckDuckGo（免费，可能被限流）
4. Bing HTML 抓取（免费兜底）
5. 全部失败 → 降级为本地 RAG 知识库

可在「系统架构」页的「网页搜索演示」直接体验，或通过 MCP 工具 `web_search` 调用。

### 4. 付费 + 人工干预

形成「**规划 → 询问确认 → 付费 → 人工确认**」闭环：

1. 客户规划好行程后，智能体会**主动询问「是否为本次行程下单」**，页面出现下单确认卡片，点击「立即下单」即可生成订单（也可在「订单中心」选择行程 → 生成支付订单，金额默认取方案预算）；
2. 客户线下转账（订单状态 `pending_payment`）；
3. 管理员在「订单中心 → 人工收款」核对到账后，**人工点击「确认收款」并填写操作人姓名**（用于审计）→ 订单状态变为 `paid`，行程同步解锁。

## 🗺️ 高德地图 & 📡 运行监控

### 高德地图（酒店真实数据）

在「**设置**」页填写高德开放平台「Web服务」Key（个人开发者免费，[申请入口](https://console.amap.com/dev/key/app)），保存即时生效；也可在 `.env` 配置 `AMAP_API_KEY`。

- 配置后：`search_hotels` 工具优先调用高德 v5 POI 检索，返回真实酒店（名称/地址/人均价/评分/精确坐标），路线规划、酒店与景点距离计算全部基于真实坐标；
- **数据源优先级**：接入 LLM 后为「高德实时数据 > 本地知识库 > LLM 生成」——酒店与景点都优先返回高德真实 POI；离线模式（未配 LLM）保持「本地精选 > 高德 > LLM 生成」；
- **长尾城市兜底**：知识库未覆盖的城市，`search_attractions` 自动走高德 POI（风景名胜类目 + 兴趣词二路检索），需求解析经地理编码验证城市，天气自动定位 —— 任意中国城市都能出方案；
- 未配置或调用失败：自动回退内置知识库数据（25 城 / 150 景点 / 100 酒店已带坐标，路线编排依旧可用）；
- 执行 `python -m scripts.enrich_geo --amap` 可将本地数据的坐标一次性替换为高德真实 POI 坐标。

### 运行监控（可观测性）

「**运行监控**」页聚焦展示两类核心调用，SSE 实时推送、打开即看：

| 事件类型 | 记录内容 |
| --- | --- |
| 🔧 tool | MCP 工具调用的参数、耗时、输出摘要与预览（如「返回 3 条结果」） |
| 🧠 llm | LLM 调用的模型、耗时、prompt 长度、输出片段、token 用量 |

后端缓冲区仍全量记录 🌐 api / 🤖 agent / 🧭 flow 事件（可用 `GET /api/monitor/events?type=...` 查询），但监控页与轮询请求自身不写入监控，数字不会自增污染。

相关接口：`GET /api/monitor/events`（历史查询）、`GET /api/monitor/summary`（汇总统计）、`GET /api/monitor/stream`（SSE 实时流）。

## 🧪 接口速览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat` | 非流式对话 |
| POST | `/api/chat/stream` | SSE 流式（agent 事件 → result） |
| GET/PUT/DELETE | `/api/plans[/{id}]` | 行程 CRUD |
| POST/GET | `/api/feedback` | 提交 / 查询反馈 |
| GET | `/api/feedback/learned` | 系统学到的经验 |
| GET/POST/DELETE | `/api/memory` | 长期记忆管理 |
| POST | `/api/knowledge/upload` | 上传资料文件入库 |
| POST | `/api/knowledge/ingest` | 粘贴文本入库 |
| GET/DELETE | `/api/knowledge/documents[/{id}]` | 资料列表 / 删除 |
| GET/POST | `/api/settings/llm` | 读取 / 保存 LLM 配置 |
| POST | `/api/settings/llm/test` | 测试 LLM 连通性 |
| GET/POST | `/api/settings/amap` | 读取 / 保存高德地图 Key |
| POST | `/api/settings/amap/test` | 测试高德 Key 连通性 |
| GET | `/api/monitor/events` | 监控事件查询（可按类型过滤） |
| GET | `/api/monitor/summary` | 监控汇总统计 |
| GET | `/api/monitor/stream` | 监控 SSE 实时流 |
| POST | `/api/orders` | 发起支付（生成订单 + 支付指引） |
| GET | `/api/orders[/pending]` | 订单列表 / 待人工确认订单 |
| POST | `/api/orders/{id}/confirm` | **人工确认收款**（记录操作人） |
| POST | `/api/orders/{id}/cancel` | 取消订单 |
| GET | `/api/search?q=` | 网页搜索（多 provider 降级） |
| GET | `/api/stats` | 系统状态 |
| GET | `/api/kb/search?q=` | RAG 检索演示 |
| GET | `/mcp` | MCP SSE 端点 |

交互式文档：http://localhost:8000/docs

## 📄 许可

MIT — 学习 / 二次开发 / 课程设计均可自由使用。
