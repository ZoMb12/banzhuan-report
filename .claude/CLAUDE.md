# 搬砖报表 — AI Agent 部署指南

CS饰品搬砖选品报表工具，基于 Streamlit。从 BUFF 市场抓取饰品 → 滑动窗口扫描价格稳定性 → Steam 市场比价 → 导出 Excel 目标清单。

---

## 一键部署（供 AI Agent 使用）

### 0. 先决条件检查

确认系统满足：
- [ ] Python >= 3.10（运行 `python --version` 检查）
- [ ] pip 已安装（运行 `pip --version` 检查）
- [ ] Git 已安装（运行 `git --version` 检查）
- [ ] 代理软件（Clash/V2Ray）已开启，监听 7890 端口（中国大陆用户必须）
- [ ] 浏览器（Chrome/Edge）可用

### 1. 克隆并安装

```bash
# 克隆仓库
git clone https://github.com/ZoMb12/banzhuan-report.git
cd banzhuan-report

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright Chromium
playwright install chromium
```

如果 `playwright install chromium` 失败，尝试：
```bash
# 指定浏览器下载路径
PLAYWRIGHT_BROWSERS_PATH=0 playwright install chromium
# 或手动设置环境变量后重试
```

### 2. 验证安装

运行以下命令验证依赖是否完整：

```bash
python -c "
import streamlit
import pandas
import requests
import openpyxl
import plotly
print('✅ 所有 Python 依赖就绪')
"
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    browser.close()
print('✅ Playwright Chromium 就绪')
"
```

### 3. 首次启动（需人工登录）

```bash
streamlit run app.py --server.port 8502
```

首次运行会弹浏览器窗口，用户需手动登录：
1. **Steam 登录** — 输入账号密码（可能需邮箱验证）
2. **BUFF 登录** — 扫码或手机验证码登录
3. 登录成功后 Cookie 保存到 `storage/`，后续无需重复登录

> **注意**：Agent 无法自动完成登录，必须在首次运行时引导用户手动操作。

### 4. 日常运行

登录一次后，后续直接运行即可自动使用持久化的 Cookie：

```bash
streamlit run app.py --server.port 8502
```

侧边栏配置参数 → 点击 **一键执行（1→4步）**。

---

## 项目结构

```
banzhuan-report/
├── app.py               # Streamlit 主入口（部署后启动此文件）
├── config.py            # 配置：代理地址、品类映射、默认参数
├── start.bat            # Windows 快捷启动
├── requirements.txt     # pip 依赖清单
├── .claude/CLAUDE.md    # 本文件 — AI Agent 交接文档
│
├── core/
│   ├── buff_scraper.py  # BUFF 市场数据抓取（Requests）
│   ├── steam_scraper.py # Steam 市场数据获取（Playwright）
│   ├── filters.py       # 滑动窗口价格稳定性扫描
│   └── excel_exporter.py# Excel 报表导出
│
├── data/
│   └── models.py        # PriceRecord / ItemSnapshot / WindowResult
│
├── utils/
│   └── helpers.py       # sleep_random 等工具函数
│
├── storage/             # Cookie + SQLite（运行时，已 gitignore）
├── exports/             # 导出的 Excel（运行时，已 gitignore）
└── 诊断/                # 错误诊断 JSON
```

---

## 核心业务流程（Agent 排查问题时参考）

### 流程概览

```
Step 1+2: BUFF 抓取 → 价格历史 → 滑动窗口筛选合格饰品
     ↓
Step 3:   按饰品分组调 Steam API → 获取对应日期价格
     ↓
Step 4:   计算 BUFF vs Steam 价差 → 筛选利润 > 0 的窗口
     ↓
导出:     生成 Excel 目标清单
```

### 关键模块

| 模块 | 文件 | 说明 |
|------|------|------|
| BUFF 数据 | `core/buff_scraper.py` | 抓取 BUFF 市场商品列表 + 价格历史 API |
| Steam 数据 | `core/steam_scraper.py` | Playwright 自动化打开 Steam 市场获取 SSR 数据 |
| 滑动窗口 | `core/filters.py` | 24 天窗口逐日扫描价格稳定性 |
| 比价筛选 | `app.py` (Step 4) | 计算均价差，筛选目标 |
| Excel 导出 | `core/excel_exporter.py` | 生成带格式的 Excel 报表 |

---

## 常见问题排查（Agent 使用）

### 问题 1：`ModuleNotFoundError`

**原因**：依赖未安装完整。
**解决**：执行 `pip install -r requirements.txt && playwright install chromium`。

### 问题 2：Steam 数据获取失败 — "无法打开 Steam 页面"

**现象**：错误日志显示 `"href导航/dispatchEvent/当前标签页降级 三种方式均失败"`。
**原因分析**：
- 代理未开启或端口不对（检查 config.py 中 `PROXY_SERVER`）
- BUFF 页面改版导致按钮选择器失效
- BUFF 反爬机制拦截
- 个别饰品偶发失败可重试，不影响整体结果

**排查步骤**：
```bash
# 1. 确认代理端口是否通
curl -x http://127.0.0.1:7890 -s -o /dev/null -w "%{http_code}" https://steamcommunity.com

# 2. 检查 Cookie 是否过期（storage/ 目录下文件）
ls -la storage/

# 3. 清除过期 Cookie 后重新登录
rm -rf storage/
```

### 问题 3：BUFF 页面超时

**现象**：`Page.goto: Timeout 60000ms exceeded`。
**原因**：网络问题或 BUFF 反爬限制。
**解决**：重试即可，偶发超时属于正常现象。

### 问题 4：Cookie 过期

**现象**：Steam 重定向到登录页。
**解决**：删除 `storage/` 目录下的 Cookie 文件，重新启动并让用户手动登录。

### 问题 5：跨设备部署

> **关键点**：`storage/`（Cookie）在 `.gitignore` 中，不会同步到 GitHub。
> 新设备首次使用需要**人工登录一次** Steam 和 BUFF。

---

## 配置文件说明

`config.py` 主要配置项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `PROXY_SERVER` | `http://127.0.0.1:7890` | 代理地址（改端口在这里） |
| `CATEGORY_OPTIONS` | 品类字典 | BUFF 品类 ID 映射 |
| `COOKIE_PATH` | `storage/buff_cookies.json` | BUFF Cookie 路径 |
| `STEAM_COOKIE_PATH` | `storage/steam_cookies.json` | Steam Cookie 路径 |

---

## 诊断工具

项目内置逐步诊断功能，在 Streamlit 界面中可针对单个商品执行分步诊断（截图 + 日志），适用于排查特定商品失败原因。

历史诊断记录存储在 `诊断/` 目录下。
