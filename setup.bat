@echo off
chcp 65001 >nul
title 搬砖报表 - 一键部署

echo ============================================
echo   搬砖报表 - 自动化部署脚本
echo ============================================
echo.

:: ---------- 检查 Python ----------
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [❌] 未检测到 Python，请先安装 Python 3.10+
    echo     下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set pyver=%%i
echo [✅] Python: %pyver%

:: ---------- 检查 pip ----------
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [❌] pip 未安装
    pause
    exit /b 1
)
echo [✅] pip 就绪

:: ---------- 安装依赖 ----------
echo.
echo [⏳] 正在安装 Python 依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [❌] 依赖安装失败
    pause
    exit /b 1
)
echo [✅] Python 依赖安装完成

:: ---------- 安装 Playwright Chromium ----------
echo.
echo [⏳] 正在安装 Playwright Chromium 浏览器...
playwright install chromium
if %errorlevel% neq 0 (
    echo [⚠️] Playwright Chromium 安装失败
    echo     可以稍后手动运行: playwright install chromium
    pause
    exit /b 1
)
echo [✅] Playwright Chromium 安装完成

:: ---------- 启动项目 ----------
echo.
echo ============================================
echo   ✅ 部署完成！
echo   正在启动搬砖报表...
echo   首次使用请在浏览器中登录 Steam 和 BUFF
echo   登录后 Cookie 会自动保存，后续无需重复登录
echo ============================================
echo.
echo 启动地址: http://localhost:8502
echo.
streamlit run app.py --server.port 8502

pause
