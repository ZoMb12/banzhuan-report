# 搬砖报表 — AI Agent 一键部署入口

> **仓库地址**：`https://github.com/ZoMb12/banzhuan-report.git`
>
> 当你（AI Agent）收到"部署这个项目"或 "clone 并运行" 的指令时，按照本文档操作。

---

## 一句话要求

克隆 → 装依赖 → 启动 → 引导用户登录。完成后用户即可在浏览器中使用。

---

## 第一步：克隆

```bash
git clone https://github.com/ZoMb12/banzhuan-report.git
cd banzhuan-report
```

## 第二步：安装

```bash
pip install -r requirements.txt
playwright install chromium
```

也可以用项目自带的自动化脚本（AI 可直接执行）：
- **Windows**: 运行 `setup.bat`
- **macOS/Linux**: 运行 `bash setup.sh`

> **验证安装** — 可选，确认一切就绪：
> ```python
> # 验证 Python 依赖
> python -c "import streamlit, pandas, requests, openpyxl, plotly; print('✅ deps ok')"
> # 验证 Playwright
> python -c "from playwright.sync_api import sync_playwright; sync_playwright().__enter__().chromium.launch(headless=True).close(); print('✅ playwright ok')"
> ```

## 第三步：启动

```bash
streamlit run app.py --server.port 8502
```

启动后会打印一个 URL（默认 `http://localhost:8502`），告诉用户打开这个地址。

## 第四步：引导用户登录

> ⚠️ **这是唯一需要用户人工操作的步骤。**

首次启动后，浏览器会自动弹出 Steam 和 BUFF 的登录页面。告知用户：
1. **登录 Steam** — 输入账号密码（可能需要邮箱验证）
2. **登录 BUFF** — 扫码或手机验证码
3. 登录成功后 Cookie 自动保存到 `storage/` 目录，**以后启动无需再登录**

## 第五步：后续使用

登录一次后，后续直接运行即可：

```bash
streamlit run app.py --server.port 8502
```

用户在浏览器中打开后，侧边栏配置参数 → 点击 **一键执行（1→4步）**。

---

## 如果遇到问题

### 依赖安装失败
```bash
# 确保 pip 是最新版
pip install --upgrade pip
# 重试依赖安装
pip install -r requirements.txt
```

### Playwright Chromium 下载慢
```bash
# 方案一：指定浏览器路径
PLAYWRIGHT_BROWSERS_PATH=0 playwright install chromium
# 方案二：仅安装依赖，使用系统已有浏览器（不推荐）
playwright install --with-deps chromium
```

### Steam 无法访问
告知用户需要开启代理（Clash/V2Ray），并确保 7890 端口可用。项目配置在 `config.py` 中，默认 `PROXY_SERVER = "http://127.0.0.1:7890"`。

### Cookie 过期
删除 `storage/` 目录，重新启动并让用户再次登录：
```bash
rm -rf storage/
```

---

## 项目速览

| 项目 | 说明 |
|------|------|
| 技术栈 | Streamlit + Playwright + Requests + pandas |
| 端口 | 8502 |
| 代理 | Clash/V2Ray :7890（中国大陆用户需要） |
| 入口文件 | `app.py` |
| 配置文件 | `config.py` |
| 关键流程 | BUFF 抓取 → 滑动窗口扫描 → Steam 比价 → Excel 导出 |

---

## 向用户汇报

部署完成后，这样告知用户：

> ✅ **搬砖报表已部署完成！**
>
> 访问地址：`http://localhost:8502`
>
> **首次使用**需要先登录一次 Steam 和 BUFF（浏览器会弹出登录页面），登录后 Cookie 会自动保存，以后再启动就不用重复登录了。
>
> 登录后，在侧边栏配置参数，点击 **一键执行** 即可开始筛选搬砖目标。
>
> 祝你搬砖愉快 🧱✨
