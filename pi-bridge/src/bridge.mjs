#!/usr/bin/env node
/**
 * Pi × TravelAgent MCP 桥接
 *
 * 架构：
 *   Pi agent-core（通用 Agent 运行时，TypeScript）
 *        │  工具调用（经 MCP 桥接适配）
 *        ▼
 *   TravelAgent MCP Server（Python FastAPI，SSE 传输 /mcp）
 *        │
 *        ▼
 *   天气 / 酒店 / 景点 / 城市指南 / RAG / 反馈 / 偏好 等 10 个旅行工具
 *
 * 证明旅行项目的工具层是「框架无关」的：LangChain 应用、Claude Desktop、
 * Pi agent 等任何 MCP 客户端都能直接接入。
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";
import { Agent } from "@earendil-works/pi-agent-core";
import {
  createModels,
  createProvider,
  envApiKeyAuth,
} from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import readline from "node:readline/promises";
import { stdin, stdout, env, exit } from "node:process";

const MCP_URL = env.TRAVEL_MCP_URL || "http://localhost:8000/mcp";

const SYSTEM_PROMPT = `你是「旅行星球」的旅行助理，由 Pi agent 驱动，所有工具经 MCP 协议调用后端 TravelAgent MCP Server。
规则：
1. 涉及天气、酒店、景点、城市信息、知识库的问题，必须先调用对应工具获取真实数据，不要凭空编造；
2. 规划行程时：先 list_cities 确认支持的城市，再组合 get_weather / search_attractions / search_hotels 给出按天安排（景点不重复、动线就近）；
3. 回答用简体中文，结构清晰，适当使用 emoji，末尾可给 1-2 条实用贴士。`;

/** LLM 配置解析：PI_LLM_*（任意 OpenAI 兼容网关）> DEEPSEEK_API_KEY > OPENAI_API_KEY */
function resolveLlmConfig() {
  if (env.PI_LLM_BASE_URL && env.PI_LLM_MODEL) {
    return { baseUrl: env.PI_LLM_BASE_URL, modelId: env.PI_LLM_MODEL, keyEnv: "PI_LLM_API_KEY" };
  }
  if (env.DEEPSEEK_API_KEY) {
    return { baseUrl: "https://api.deepseek.com/v1", modelId: env.PI_LLM_MODEL || "deepseek-chat", keyEnv: "DEEPSEEK_API_KEY" };
  }
  if (env.OPENAI_API_KEY) {
    return { baseUrl: "https://api.openai.com/v1", modelId: env.PI_LLM_MODEL || "gpt-4o-mini", keyEnv: "OPENAI_API_KEY" };
  }
  return null;
}

/** 连接 TravelAgent MCP Server（SSE 传输） */
async function connectMcp() {
  const transport = new SSEClientTransport(new URL(MCP_URL));
  const client = new Client({ name: "pi-travel-bridge", version: "0.1.0" });
  await client.connect(transport);
  return client;
}

/** MCP 工具描述 → pi-agent-core AgentTool（JSON Schema 直接复用） */
function toPiTools(client, mcpTools) {
  return mcpTools.map((t) => ({
    name: t.name,
    label: t.name,
    description: t.description || "",
    parameters: t.inputSchema,
    execute: async (_toolCallId, params) => {
      const res = await client.callTool({ name: t.name, arguments: params ?? {} });
      const text =
        (res.content ?? [])
          .filter((c) => c.type === "text")
          .map((c) => c.text)
          .join("\n") || "(工具返回为空)";
      return { content: [{ type: "text", text }], details: { structured: res.structuredContent ?? null } };
    },
  }));
}

/** 注册 OpenAI 兼容 Provider（DeepSeek / 通义 DashScope / OneAPI / OpenAI 均可） */
function buildModels(cfg) {
  const model = {
    id: cfg.modelId,
    name: `${cfg.modelId}（OpenAI 兼容网关）`,
    api: "openai-completions",
    provider: "travel-llm",
    baseUrl: cfg.baseUrl,
    reasoning: false,
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 131072,
    maxTokens: 8192,
    // DashScope / DeepSeek 等兼容网关不认 developer 角色与 reasoning_effort
    compat: { supportsDeveloperRole: false, supportsReasoningEffort: false },
  };
  const provider = createProvider({
    id: "travel-llm",
    name: "Travel LLM",
    baseUrl: cfg.baseUrl,
    auth: { apiKey: envApiKeyAuth("LLM API Key", [cfg.keyEnv]) },
    models: [model],
    api: openAICompletionsApi(),
  });
  const models = createModels();
  models.setProvider(provider);
  return { models, model };
}

async function main() {
  const mode = process.argv[2];

  process.stdout.write(`⏳ 连接 TravelAgent MCP Server（${MCP_URL}）…\n`);
  const client = await connectMcp();
  const tools = toPiTools(client, (await client.listTools()).tools);

  // 模式一：只列出 MCP 工具（无需 LLM Key，用于连通性验证）
  if (mode === "--list-tools") {
    console.log(`✅ 已连接，发现 ${tools.length} 个 MCP 工具：`);
    for (const t of tools) console.log(`  🔧 ${t.name.padEnd(22)} ${t.description}`);
    await client.close();
    return;
  }

  const cfg = resolveLlmConfig();
  if (!cfg || !env[cfg.keyEnv]) {
    console.error(
      "❌ 缺少 LLM 配置：请在 .env（或环境变量）中设置 PI_LLM_BASE_URL / PI_LLM_MODEL / PI_LLM_API_KEY，" +
        "或只填 DEEPSEEK_API_KEY / OPENAI_API_KEY。参考 .env.example",
    );
    await client.close();
    exit(1);
  }

  const { models, model } = buildModels(cfg);
  const agent = new Agent({
    initialState: { systemPrompt: SYSTEM_PROMPT, model, tools },
    streamFn: models.streamSimple.bind(models),
  });

  agent.subscribe((event) => {
    if (event.type === "message_update" && event.assistantMessageEvent?.type === "text_delta") {
      process.stdout.write(event.assistantMessageEvent.delta);
    } else if (event.type === "tool_execution_start") {
      const args = JSON.stringify(event.args ?? {});
      process.stdout.write(`\n  🔧 [MCP] ${event.toolName}${args === "{}" ? "()" : `(${args})`}\n`);
    }
  });

  // 模式二：单次提问（烟测用）
  if (mode === "--ask") {
    const question = process.argv[3];
    if (!question) {
      console.error('用法：node src/bridge.mjs --ask "北京有什么推荐的景点？"');
      await client.close();
      exit(1);
    }
    await agent.prompt(question);
    process.stdout.write("\n");
  } else {
    // 模式三：交互式对话
    console.log(`✅ Pi × TravelAgent 桥接就绪（MCP: ${MCP_URL} ｜ 模型: ${cfg.modelId}）`);
    console.log("输入旅行需求，例如「杭州两天怎么玩？预算舒适型」；输入 exit 退出\n");
    const rl = readline.createInterface({ input: stdin, output: stdout });
    for (;;) {
      const line = (await rl.question("你 > ")).trim();
      if (!line) continue;
      if (line === "exit" || line === "quit") break;
      process.stdout.write("Pi > ");
      await agent.prompt(line);
      process.stdout.write("\n\n");
    }
    rl.close();
  }

  await client.close();
}

main().catch((e) => {
  console.error("❌ 桥接错误：", e?.message ?? e);
  console.error("提示：请确认后端已启动（cd backend && python -m uvicorn app.main:app --port 8000）");
  process.exit(1);
});
