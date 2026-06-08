#!/usr/bin/env bash
set -e

echo "============================================"
echo "  搬砖报表 - 自动化部署脚本"
echo "============================================"
echo ""

# ---------- 检查 Python ----------
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[❌] 未检测到 Python，请先安装 Python 3.10+"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)
PYVER=$($PYTHON --version 2>&1)
echo "[✅] $PYVER"

# ---------- 检查 pip ----------
if ! command -v pip3 &>/dev/null && ! command -v pip &>/dev/null; then
    echo "[❌] pip 未安装"
    exit 1
fi

PIP=$(command -v pip3 || command -v pip)
echo "[✅] pip 就绪"

# ---------- 安装依赖 ----------
echo ""
echo "[⏳] 正在安装 Python 依赖..."
$PIP install -r requirements.txt
echo "[✅] Python 依赖安装完成"

# ---------- 安装 Playwright Chromium ----------
echo ""
echo "[⏳] 正在安装 Playwright Chromium 浏览器..."
$PLAY install chromium 2>/dev/null || $PYTHON -m playwright install chromium
echo "[✅] Playwright Chromium 安装完成"

# ---------- 启动 ----------
echo ""
echo "============================================"
echo "  ✅ 部署完成！"
echo "  正在启动搬砖报表..."
echo "  首次使用请在浏览器中登录 Steam 和 BUFF"
echo "============================================"
echo ""
echo "启动地址: http://localhost:8502"
echo ""

$PYTHON -m streamlit run app.py --server.port 8502
