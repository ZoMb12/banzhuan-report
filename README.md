# 搬砖报表

CS 饰品搬砖选品报表工具。从 BUFF 市场抓取饰品，通过滑动窗口扫描价格稳定性，与 Steam 市场比价，导出 Excel 目标清单。

## 功能

- **多品类抓取**：支持匕首、手套、步枪、手枪等多品类同时抓取
- **价格稳定性分析**：24 天滑动窗口逐日扫描，筛选波动在阈值内的饰品
- **Steam 比价**：自动打开 Steam 市场获取历史价格（BUFF 日期 -7 天），计算均价差
- **Excel 导出**：仅导出有利润空间的目标饰品，按时间点逐行列出 BUFF/Steam 价格
- **一键执行**：分步状态追踪，每步可单独重试
- **诊断工具**：BUFF / Steam 数据提取逐步诊断

## 安装

### 系统要求

| 项目 | 要求 |
|------|------|
| Python | 3.10+（推荐 3.11+） |
| 代理 | Clash / V2Ray，**7890 端口**（Steam 需要，大陆用户必装） |
| 账号 | Steam 账号 + BUFF 账号 |
| 浏览器 | Chrome / Edge（首次登录用） |

### 安装步骤

```bash
# 1. 拉取代码
git clone https://github.com/ZoMb12/banzhuan-report.git
cd banzhuan-report

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 安装 Playwright Chromium 浏览器（用于 Steam 自动化）
playwright install chromium
```

> **注意**：如果 `playwright install chromium` 下载慢，可以手动下载 Chromium 并设置 `PLAYWRIGHT_BROWSERS_PATH` 环境变量。

## 首次使用

### 1. 配置代理

编辑 `config.py`，确认代理地址（默认 `http://127.0.0.1:7890`）：

```python
PROXY_SERVER = "http://127.0.0.1:7890"
```

确保代理软件（Clash / V2Ray）已开启并监听 7890 端口。

### 2. 启动并登录

```bash
streamlit run app.py --server.port 8502
```

或双击 `start.bat`。

首次启动后，系统会弹出浏览器窗口要求登录 **Steam** 和 **BUFF**。登录成功后 Cookie 自动保存到本地 `storage/` 目录，后续无需重复登录。

> **Cookie 安全**：`storage/` 已加入 `.gitignore`，不会上传到 GitHub。

### 3. 运行

侧边栏配置参数后，点击 **一键执行（1→4步）**。

## 核心流程

```
BUFF 抓取 → 价格历史 → 滑动窗口扫描 → Steam 比价 → 利润筛选 → Excel 导出
```

1. **抓取 + 扫描（合并）**：从 BUFF 市场抓取饰品 → 拉取近一年价格历史 → 24 天窗口逐日滑动扫描 → 记录波动在阈值内的合格窗口
2. **Steam 比价**：按饰品汇总 BUFF 窗口日期，调用 Steam 获取对应日期（-7天）的价格
3. **筛选导出**：按窗口均价差 > 0 判定为目标饰品，生成 Excel

## 技术栈

| 技术 | 用途 |
|------|------|
| **Streamlit** | Web UI 框架 |
| **Playwright** | 浏览器自动化（Steam 数据获取） |
| **Requests** | HTTP 请求（BUFF API） |
| **pandas** | 数据处理 |
| **openpyxl** | Excel 报表生成 |
| **plotly** | 价格对比图表 |

## 项目结构

```
banzhuan-report/
├── app.py               # Streamlit 主界面
├── config.py            # 默认参数配置 + 代理/品类配置
├── start.bat            # 快捷启动（Windows）
├── requirements.txt     # Python 依赖清单
├── .claude/CLAUDE.md    # AI 代理部署/交接文件
├── core/
│   ├── buff_scraper.py  # BUFF 市场抓取 + 价格历史 API
│   ├── steam_scraper.py # Steam 市场数据获取（Playwright）
│   ├── filters.py       # 价格稳定性 + 滑动窗口扫描
│   └── excel_exporter.py# Excel 报表生成
├── data/
│   └── models.py        # 数据模型
├── utils/
│   └── helpers.py       # 工具函数
├── storage/             # Cookie 和数据库（运行时创建，已 gitignore）
├── exports/             # Excel 导出目录（运行时创建，已 gitignore）
└── 诊断/                # 错误诊断 JSON 记录
```

## 常见问题

### Q: 启动时报错 `ModuleNotFoundError`

确保已执行 `pip install -r requirements.txt` 和 `playwright install chromium`。

### Q: Steam 数据获取失败

- 检查代理是否已开启，7890 端口是否可用
- 检查 Cookie 是否过期（删除 `storage/` 下文件后重新登录）
- 个别饰品偶发失败不影响整体结果，可在界面中重试

### Q: 端口 8502 被占用

```bash
streamlit run app.py --server.port 你的端口号
```

### Q: 如何跨设备同步？

项目代码通过 GitHub 同步，但 `storage/`（Cookie）不会被推送。新设备首次使用需要重新登录一次 Steam 和 BUFF。

## 注意事项

- Steam 在中国大陆需要代理访问，**必须开启代理**才能获取 Steam 价格
- Cookie 存储在本地 `storage/`，不会上传到 GitHub，请妥善保管
- 首次使用必须手动登录一次 Steam 和 BUFF
- 诊断目录 `诊断/` 包含历史错误报告，可用于排查问题
