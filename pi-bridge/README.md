# 🌉 Pi × TravelAgent MCP 桥接

用 [Pi agent](https://github.com/earendil-works/pi)（`@earendil-works/pi-agent-core`，TypeScript）作为**通用 Agent 运行时**，经 **MCP 协议**驱动本项目的旅行工具——证明 TravelAgent 的工具层是**框架无关**的：LangChain 应用、Claude Desktop、Cursor、Pi 等任何 MCP 客户端都能直接接入。

```
终端里的你
   │  自然语言（如「北京有什么好玩的？」）
   ▼
Pi agent（pi-agent-core，Node/TS）──────── LLM（OpenAI 兼容网关）
   │  模型决定调用工具
   ▼
MCP 桥接适配层（本目录 src/bridge.mjs）
   │  MCP JSON-RPC（SSE 传输）
   ▼
TravelAgent MCP Server（Python FastAPI，GET /mcp + POST /mcp/messages/）
   │
   ▼
🔧 get_weather / search_hotels / search_attractions / kb_search / web_search … 共 10 个工具
```

## 快速开始

```bash
# 1. 启动旅行后端（MCP 服务随应用挂载）
cd backend && pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000

# 2. 安装桥接依赖（Node ≥ 20.6）
cd pi-bridge && npm install

# 3. 配置 LLM（桥接侧直连大模型，与后端的 LLM 配置互不影响）
copy .env.example .env        # 填入 DeepSeek / 通义 / OpenAI 任一 Key

# 4. 运行
npm run list-tools            # 列出后端暴露的全部 MCP 工具（无需 LLM Key）
npm run ask -- "北京有什么推荐的景点？"     # 单次提问
npm start                     # 交互式对话
```

## 三种模式

| 命令 | 说明 |
| --- | --- |
| `npm run list-tools` | 连接后端并列出全部 MCP 工具（连通性验证，零 LLM 成本） |
| `npm run ask -- "问题"` | 单次提问：Agent 自动决定调用哪些工具，回答后退出 |
| `npm start` | 交互式 REPL：多轮对话，`exit` 退出 |

运行效果示例：

```
你 > 北京有哪些值得去的景点？推荐两个就行
Pi > 我来为您推荐北京两个非常值得去的景点！首先让我查询一下北京的热门景点信息：

  🔧 [MCP] search_attractions({"city":"北京","top_k":2})

为您精选北京两大必去景点 🌟：
1. 故宫博物院 🏯 —— 门票 ¥60（需提前预约）…
2. 八达岭长城 🐉 —— 门票 ¥40（含摆渡车）…
```

## 工作原理

1. **MCP 连接**：`@modelcontextprotocol/sdk` 的 `SSEClientTransport` 连接后端 `GET /mcp`（SSE 流），客户端→服务端消息走 `POST /mcp/messages/`；
2. **工具发现与适配**：`client.listTools()` 拿到 MCP 工具清单（名称/描述/JSON Schema 入参），原样映射为 pi-agent-core 的 `AgentTool`（MCP 的 inputSchema 本就是 JSON Schema，与 Pi 使用的 TypeBox 同源），`execute` 内转发为 `client.callTool()`；
3. **Agent 循环**：`pi-ai` 的 `createProvider()` 注册一个 OpenAI 兼容 Provider（DeepSeek / 通义 DashScope / OneAPI / OpenAI 均可），`Agent` 收到用户消息 → LLM 决定调用哪个 MCP 工具 → 桥接执行并回填结果 → 循环直到给出最终回答；
4. **全异步流式**：文本增量（`text_delta`）与工具执行事件（`tool_execution_start`）实时打印到终端。

## LLM 配置说明

桥接侧的 LLM 只影响「Pi 怎么思考和决策」，与后端的 LLM 配置（设置页/.env）完全独立，互不影响：

| 方式 | 环境变量 |
| --- | --- |
| 任意 OpenAI 兼容网关（推荐） | `PI_LLM_BASE_URL` + `PI_LLM_MODEL` + `PI_LLM_API_KEY` |
| DeepSeek 官方端点 | 只填 `DEEPSEEK_API_KEY`（自动 `https://api.deepseek.com/v1` + `deepseek-chat`） |
| OpenAI 官方端点 | 只填 `OPENAI_API_KEY`（自动 `gpt-4o-mini`） |

> 本地模型也可以：把 `PI_LLM_BASE_URL` 指到 Ollama / vLLM / LM Studio 的 OpenAI 兼容端点即可（如 `http://localhost:11434/v1`）。

## 常见问题

- **连接 404 / ECONNREFUSED**：后端没启动，或端口不是 8000 —— 先 `python -m uvicorn app.main:app --port 8000`，或用 `TRAVEL_MCP_URL` 指向实际地址；
- **工具列表为空 / 报错**：确认后端版本包含 `app/mcp_server/travel_mcp.py`（首次启动自动构建 RAG 索引约 1-3 秒）；
- **LLM 报鉴权错误**：检查 `.env` 中的 Key 与网关地址是否匹配（DashScope 需用 `compatible-mode/v1` 端点）。
