# ===== TravelAgent 一键启动脚本（Windows） =====
# 用法：右键"使用 PowerShell 运行"，或执行  .\start.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "`n✈️  旅行星球 TravelAgent 启动器" -ForegroundColor Cyan
Write-Host "================================"

# 1) 后端依赖
Write-Host "`n[1/4] 检查后端依赖..." -ForegroundColor Yellow
Push-Location "$Root\backend"
python -c "import fastapi, mcp, chromadb, rank_bm25" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  安装后端依赖（首次运行，约 1-2 分钟）..." -ForegroundColor Yellow
    pip install -r requirements.txt
} else {
    Write-Host "  依赖已就绪"
}

# 2) 知识库（幂等）
Write-Host "`n[2/4] 生成知识库语料..." -ForegroundColor Yellow
if (-not (Test-Path "data\knowledge\city_meta.json")) {
    python -m scripts.generate_knowledge
} else {
    Write-Host "  知识库已存在"
}
Pop-Location

# 3) 前端依赖
Write-Host "`n[3/4] 检查前端依赖..." -ForegroundColor Yellow
Push-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "  安装前端依赖（首次运行，约 1-2 分钟）..." -ForegroundColor Yellow
    npm install
} else {
    Write-Host "  依赖已就绪"
}
Pop-Location

# 4) 启动服务
Write-Host "`n[4/4] 启动服务..." -ForegroundColor Green
Write-Host "  后端: http://localhost:8000  (API 文档 /docs)" -ForegroundColor Green
Write-Host "  前端: http://localhost:5173" -ForegroundColor Green
Write-Host "  按 Ctrl+C 停止`n" -ForegroundColor DarkGray

Push-Location "$Root\backend"
$backend = Start-Process python -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000" -WindowStyle Hidden -PassThru
Pop-Location

Start-Sleep -Seconds 5
Push-Location "$Root\frontend"
npm run dev
Pop-Location

# 清理
if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
Write-Host "`n服务已停止。" -ForegroundColor Cyan
