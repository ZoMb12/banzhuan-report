# 搬砖报表

CS 饰品搬砖选品报表工具。从 BUFF 市场抓取饰品，通过滑动窗口扫描价格稳定性，与 Steam 市场比价，导出 Excel 目标清单。

## 功能

- **多品类抓取**：支持匕首、手套、步枪、手枪等多品类同时抓取
- **价格稳定性分析**：24 天滑动窗口逐日扫描，筛选波动在阈值内的饰品
- **Steam 比价**：自动打开 Steam 市场获取历史价格（BUFF 日期 -7 天），计算均价差
- **Excel 导出**：仅导出有利润空间的目标饰品，按时间点逐行列出 BUFF/Steam 价格
- **一键执行**：分步状态追踪，每步可单独重试
- **诊断工具**：BUFF / Steam 数据提取逐步诊断

## 快速开始

### 前置条件

- Python 3.10+
- Steam 账号（需在浏览器登录过）
- BUFF 账号（需在浏览器登录过）
- 本地代理（Clash / V2Ray，默认端口 7890），用于访问 Steam

### 安装

```bash
git clone https://github.com/ZoMb12/banzhuan-report.git
cd banzhuan-report
pip install -r requirements.txt
playwright install chromium
```

### 配置代理（首次使用）

编辑 `config.py`，确认代理地址：

```python
PROXY_SERVER = "http://127.0.0.1:7890"
```

### 登录 BUFF 和 Steam

启动后首次使用需在浏览器弹窗中登录：

```bash
streamlit run app.py --server.port 8502
```

或双击 `start.bat`。

登录成功后 Cookie 会持久化到 `storage/` 目录，后续无需重复登录。

### 运行

侧边栏配置参数后，点击 **一键执行（1→4步）**。

## 核心流程

```
BUFF 抓取 → 价格历史 → 滑动窗口扫描 → Steam 比价 → 利润筛选 → Excel 导出
```

1. **抓取 + 扫描（合并）**：从 BUFF 市场抓取饰品 → 拉取近一年价格历史 → 24 天窗口逐日滑动扫描 → 记录波动在阈值内的合格窗口
2. **Steam 比价**：按饰品汇总 BUFF 窗口日期，调用 Steam 获取对应日期（-7天）的价格
3. **筛选导出**：按窗口均价差 > 0 判定为目标饰品，生成 Excel

## 项目结构

```
app.py              # Streamlit 主界面
config.py           # 默认参数配置
core/
  buff_scraper.py   # BUFF 市场抓取 + 价格历史 API
  steam_scraper.py  # Steam 市场数据获取（Playwright）
  filters.py        # 价格稳定性 + 滑动窗口扫描
  excel_exporter.py # Excel 报表生成
data/
  models.py         # 数据模型
utils/
  helpers.py        # 工具函数
storage/            # Cookie（已 gitignore）
exports/            # 导出 Excel（已 gitignore）
```

## 技术栈

- **Streamlit** — Web UI
- **Playwright** — 浏览器自动化（Steam 数据）
- **Requests** — HTTP 请求（BUFF API）
- **openpyxl** — Excel 生成

## 注意事项

- Steam 在中国大陆需要代理访问，默认使用 Clash/V2Ray 7890 端口
- Cookie 存储在本地 `storage/` 目录，不会上传到 GitHub
- 首次使用 Steam 功能需要先手动登录一次
