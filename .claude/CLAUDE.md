# 搬砖报表

CS饰品搬砖选品报表工具，基于 Streamlit。从 BUFF 市场抓取饰品 → 24天滑动窗口扫描价格稳定性 → Steam 市场比价 → 导出 Excel 目标清单。

## 启动

```bash
streamlit run app.py --server.port 8502
```

或双击 `start.bat`。

## 核心流程

1. **第一、二步（合并）**：从 BUFF 当前市场抓取饰品 → 拉取近一年价格历史 → 24 天窗口逐日滑动扫描 → 记录所有波动在阈值内的合格窗口
2. **第三步**：按饰品汇总所有窗口的 BUFF 日期，统一调 Steam API（日期 −7 天），数据分发回各窗口
3. **第四步**：按窗口均价差 > 0 判定目标饰品，生成逐时间点对比数据
4. **导出 Excel**：仅导出目标饰品，按时间点逐行列出 BUFF/Steam 价格

## 关键配置（侧边栏）

- 价格稳定考察天数：默认 24
- 价格波动阈值：默认 5%
- 历史回溯天数：默认 365
- USD → CNY 汇率：默认 7.2
- 饰品品类：支持多品类筛选（匕首、手套、步枪等）

## Bug Fixes（从 cs-test 原项目同步）

### Steam 数据提取
- 增加代理支持（Clash/V2Ray 7890），解决 Steam 被墙问题
- `_click_and_get_steam_page()`：3 种方式打开 Steam（href 直接导航 → dispatchEvent → 当前标签页降级），绕过验证码遮罩
- `_try_add_cookies()`：修复 sameSite cookie 兼容性
- `get_steam_market_data()`：支持 2 次重试、`?cc=us` 强制美元计价、BUFF 页面错误检测、Steam 登录重定向检测
- 按皮肤名分组批处理（`get_steam_market_data_batch`），同组共用一个 Steam 页面，显著提速
- 结构化错误追踪（`_last_error` + `_last_error_context` + `_batch_errors`）
- 失败饰品重试机制（`retry_steam_failed_items`）

### BUFF 数据提取
- 多品类抓取支持，各品类独立翻页，数量均分 + 动态补齐
- `get_items_on_date()` 支持 `target_count`、`categories`、`min_price`、`min_volume` 参数
- 多品类去重

### 界面改进
- 错误日志面板（`_log_error` + `_show_error_log`）
- 一键执行带分步状态追踪
- 参数变更检测
- Plotly 价格对比图表
- BUFF/Steam 逐步诊断工具
- 分步重试按钮

## 项目结构

```
app.py              # Streamlit 主界面
config.py           # 默认参数配置 + 代理/品类配置
core/
  buff_scraper.py   # BUFF 市场抓取 + 价格历史 API（支持多品类）
  steam_scraper.py  # Steam 市场数据获取（Playwright，支持代理/批处理/重试）
  filters.py        # 价格稳定性 + 滑动窗口扫描
  excel_exporter.py # Excel 报表生成（openpyxl）
data/
  models.py         # PriceRecord, ItemSnapshot, WindowResult
utils/
  helpers.py        # sleep_random 工具函数
storage/            # Cookie 和数据库（运行时创建）
exports/            # Excel 导出目录（运行时创建）
```

## 注意事项

- 需要 BUFF 和 Steam 登录态（Cookie 持久化在 storage/）
- Steam 访问需本地代理（默认 Clash/V2Ray 7890）
- Steam 数据通过 Playwright 无头浏览器获取
- 端口 8502（8501 已被原 cs-test 项目占用）
