#!/usr/bin/env bash
# TravelAgent 一键启动脚本（macOS / Linux / WSL）
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "✈️  旅行星球 TravelAgent 启动器"
echo "================================"

echo -e "\n[1/4] 检查后端依赖..."
cd "$ROOT/backend"
python3 -c "import fastapi, mcp, chromadb, rank_bm25" 2>/dev/null || {
  echo "  安装后端依赖..."
  pip3 install -r requirements.txt
}

echo -e "\n[2/4] 生成知识库语料..."
[ -f "data/knowledge/city_meta.json" ] || python3 -m scripts.generate_knowledge

echo -e "\n[3/4] 检查前端依赖..."
cd "$ROOT/frontend"
[ -d "node_modules" ] || npm install

echo -e "\n[4/4] 启动服务..."
echo "  后端: http://localhost:8000  (API 文档 /docs)"
echo "  前端: http://localhost:5173"
echo "  按 Ctrl+C 停止"
echo ""

cd "$ROOT/backend"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 4
cd "$ROOT/frontend"
npm run dev
kill $BACKEND_PID 2>/dev/null || true
