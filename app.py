from datetime import date, timedelta

import pandas as pd
import streamlit as st

import config
from core.buff_scraper import (
    diagnose_price_extraction, ensure_login, get_full_price_history,
    get_items_on_date, get_price_history, is_logged_in, open_buff_page,
)
from core.steam_scraper import (
    diagnose_steam_extraction, ensure_steam_login,
    get_steam_market_data, is_steam_logged_in, open_steam_market,
)
import core.steam_scraper as _steam
from core.filters import apply_initial_filters, find_stable_windows
from core.excel_exporter import export_to_excel
from data.models import ItemSnapshot, WindowResult
from utils.helpers import sleep_random

st.set_page_config(page_title="搬砖报表", layout="wide")

# 隐藏 Streamlit 默认元素
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

st.title("搬砖报表")
st.caption("滑动窗口扫描 · 24天稳定性筛选 · Steam比价 · Excel导出")

today = date.today()


# ---------- 错误日志 ----------
def _log_error(step: int, item_id: str, item_name: str, error: str,
               context: dict = None):
    from datetime import datetime as _dt
    entry = {
        "step": step, "item_id": item_id,
        "item_name": item_name[:60] if item_name else "",
        "error": error, "time": _dt.now().strftime("%H:%M:%S"),
    }
    if context:
        entry["context"] = context
    st.session_state.error_log.append(entry)


def _show_error_log():
    errors = st.session_state.get("error_log", [])
    if not errors:
        return
    step_names = {1: "滑动窗口筛选", 2: "Steam数据", 3: "比价筛选"}
    with st.expander(f"⚠️ 错误日志（{len(errors)} 条）", expanded=len(errors) > 0):
        for e in errors:
            icon = "❌"
            step_label = step_names.get(e["step"], f"Step{e['step']}")
            item_label = f" [{e['item_name']}]" if e["item_name"] else ""
            ctx = e.get("context")
            ctx_summary = ""
            if ctx:
                ctx_summary = f" [{ctx.get('type','')}] {str(ctx.get('detail',''))[:60]}"
            st.caption(
                f"{icon} **Step{e['step']}·{step_label}**{item_label}"
                f" — {e['error']}{ctx_summary}  `{e['time']}`"
            )
            if ctx:
                with st.status("", expanded=False):
                    for k, v in ctx.items():
                        val = str(v)
                        if len(val) > 300:
                            val = val[:300] + "..."
                        st.code(f"{k}: {val}")


def _snapshot_params():
    st.session_state._param_snapshot = {
        "stable_days": stable_days,
        "volatility_threshold": volatility_threshold,
        "target_count": target_count,
        "lookback_days": lookback_days,
        "conversion_rate": conversion_rate,
    }


# ---------- 侧边栏参数配置 ----------
with st.sidebar:
    st.header("参数配置")

    stable_days = st.number_input(
        "价格稳定考察天数", min_value=1, max_value=90, value=config.DEFAULT_STABLE_DAYS
    )
    volatility_threshold = st.slider(
        "价格波动阈值 (%)", min_value=1, max_value=30, value=5
    ) / 100.0
    target_count = st.number_input(
        "目标饰品数量", min_value=10, max_value=2000, value=config.DEFAULT_TARGET_COUNT, step=10,
        help="BUFF 端初步筛选的目标饰品数量",
    )
    lookback_days = st.number_input(
        "历史回溯天数", min_value=30, max_value=730,
        value=config.DEFAULT_LOOKBACK_DAYS,
        help="从今天往前回溯多少天来扫描滑动窗口",
    )

    st.divider()
    st.subheader("卡价转换比")
    conversion_rate = st.number_input(
        "卡价转换比（美元 → 人民币）",
        min_value=0.1, max_value=20.0, value=7.2, step=0.01,
        help="用于将 Steam 美元价格转换为人民币",
    )

    st.divider()
    st.subheader("BUFF 筛选条件")
    category_names = st.multiselect(
        "饰品品类",
        options=list(config.CATEGORY_OPTIONS.keys()),
        default=["全部/不限"],
        help="可多选。选「全部/不限」或全不选时不做品类限制",
    )

    st.divider()
    if is_logged_in():
        if st.button("查看 BUFF 页面", use_container_width=True):
            with st.spinner("正在打开 BUFF 页面..."):
                open_buff_page()
            st.success("浏览器窗口已关闭")
    else:
        if st.button("登录 BUFF", use_container_width=True):
            with st.spinner("正在打开浏览器，请完成登录..."):
                ensure_login()
            if is_logged_in():
                st.success("登录态已保存")
            else:
                st.error("未检测到登录态，请重新尝试")

    st.divider()
    if is_steam_logged_in():
        if st.button("查看 Steam 市场", use_container_width=True):
            with st.spinner("正在打开 Steam 市场..."):
                open_steam_market()
            st.success("浏览器窗口已关闭")
    else:
        if st.button("登录 Steam 账号", use_container_width=True):
            with st.spinner("正在打开浏览器，请完成 Steam 登录..."):
                ensure_steam_login()
            if is_steam_logged_in():
                st.success("Steam 登录态已保存")
            else:
                st.error("未检测到 Steam 登录态，请重新尝试")

    st.divider()
    st.caption(
        f"配置预览：\n"
        f"- 滑动窗口：{stable_days} 天\n"
        f"- 波动阈值：≤{volatility_threshold * 100:.0f}%\n"
        f"- 历史回溯：{lookback_days} 天\n"
        f"- 目标饰品数量：{target_count}\n"
        f"- 汇率：1 USD = {conversion_rate} CNY"
    )

    # 参数变更检测（分步模式）
    _snap = st.session_state.get("_param_snapshot")
    if _snap and st.session_state.get("one_click_mode") is None:
        affected = []
        if st.session_state.get("stage1_done"):
            if (stable_days != _snap.get("stable_days") or
                volatility_threshold != _snap.get("volatility_threshold") or
                lookback_days != _snap.get("lookback_days")):
                affected.append("Step 1+2 窗口/阈值/回溯")
        if st.session_state.get("stage3_done"):
            if conversion_rate != _snap.get("conversion_rate"):
                affected.append("Step 4 汇率转换比")
        if affected:
            st.warning("参数已修改，影响已完成步骤：\n" + "\n".join(f"• {a}" for a in affected) +
                       "\n建议重新执行受影响的步骤")


# ---------- 主区域 ----------
tabs = st.tabs(["筛选流程", "价格走势"])

with tabs[0]:
    # ---- 初始化 session_state ----
    defaults = {
        "stage1_done": False, "items_from_buff": [],
        "stage2_done": False, "qualifying_windows": [],
        "stage3_done": False, "steam_data_by_item": {},
        "stage4_done": False, "export_path": "",
        "one_click_mode": None,
        "error_log": [],
        "failed_step3_items": [],
        "_param_snapshot": None,
        "_run_conversion_rate": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    one_click_mode = st.session_state.one_click_mode

    # =====================================================================
    # 一键获取完成展示
    # =====================================================================
    if one_click_mode == "done" and st.session_state.stage4_done:
        windows = st.session_state.qualifying_windows
        target_windows = [w for w in windows if w.is_target]
        _disp_rate = st.session_state.get("_run_conversion_rate", conversion_rate)

        st.success(f"全流程完成！共 {len(windows)} 个合格窗口，{len(target_windows)} 个目标窗口")

        # ── 分步状态与重新执行按钮 ──
        st.divider()
        s1_count = len(st.session_state.qualifying_windows)
        s3_count = len([w for w in windows if w.steam_avg_price_usd is not None])
        s4_count = len(target_windows)

        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            st.metric("Step 1+2 滑动窗口", f"{s1_count} 个窗口")
            if st.button("🔄 重新执行 Step 1→4", key="redo_all", use_container_width=True):
                st.session_state.one_click_mode = None
                st.session_state.stage1_done = False
                st.session_state.stage2_done = False
                st.session_state.stage3_done = False
                st.session_state.stage4_done = False
                st.session_state.export_path = ""
                st.session_state.error_log = []
                st.rerun()
        with col_r2:
            st.metric("Step 3 Steam数据", f"{s3_count}/{s1_count}")
        with col_r3:
            st.metric("Step 4 目标窗口", f"{s4_count}")
            if st.button("🔄 重新执行 Step 3→4", key="redo_s34", use_container_width=True):
                st.session_state.stage2_done = False
                st.session_state.stage3_done = False
                st.session_state.stage4_done = False
                st.session_state.one_click_mode = None
                st.rerun()

        # ── 失败饰品重试 ──
        _failed_step3 = st.session_state.get("failed_step3_items", [])
        if _failed_step3:
            st.divider()
            with st.expander(f"🔄 重试失败饰品（{len(_failed_step3)} 条）", expanded=False):
                for fi in _failed_step3:
                    name = fi["buff_item_name"]
                    col_a, col_b = st.columns([4, 1])
                    with col_a:
                        st.caption(f"{name}  (ID: {fi['item_id']})")
                    with col_b:
                        if st.button("重试", key=f"retry_{fi['item_id']}", use_container_width=True):
                            with st.spinner(f"正在重试 {name}..."):
                                result = _steam.get_steam_market_data(
                                    fi["item_id"], fi["target_dates"], fi["buff_item_name"],
                                )
                            if result:
                                st.session_state.steam_data_by_item[fi["item_id"]] = result
                                st.session_state.failed_step3_items = [
                                    f for f in st.session_state.failed_step3_items
                                    if f["item_id"] != fi["item_id"]
                                ]
                                st.success(f"✅ {name} 重试成功")
                                st.rerun()
                            else:
                                err = _steam.get_last_steam_error(item_id=fi["item_id"]) or "未知错误"
                                _log_error(3, fi["item_id"], name, err)
                                st.error(f"❌ {name} 重试失败: {err}")

                if st.button("🔄 重试全部失败饰品", type="primary",
                              use_container_width=True, key="retry_all"):
                    with st.spinner(f"正在批量重试 {len(_failed_step3)} 个失败饰品..."):
                        batch_result = _steam.retry_steam_failed_items(_failed_step3)
                    ok = 0
                    for fi in _failed_step3:
                        data = batch_result.get(fi["item_id"])
                        if data:
                            st.session_state.steam_data_by_item[fi["item_id"]] = data
                            ok += 1
                    st.session_state.failed_step3_items = [
                        f for f in _failed_step3 if f["item_id"] not in batch_result
                    ]
                    if ok == len(_failed_step3):
                        st.success(f"✅ 全部重试成功: {ok}/{len(_failed_step3)}")
                    elif ok > 0:
                        st.warning(f"部分重试成功: {ok}/{len(_failed_step3)}，剩余 {len(_failed_step3)-ok} 条仍失败")
                    else:
                        st.error(f"全部重试失败: 0/{len(_failed_step3)}，请检查代理或Steam登录状态")
                    st.rerun()

        # ── 目标饰品展示 ──
        if target_windows:
            st.divider()
            st.header(f"🎯 目标饰品（{len(target_windows)} 个目标窗口）")

            # 按饰品汇总
            item_summary = {}
            for w in target_windows:
                if w.item_id not in item_summary:
                    item_summary[w.item_id] = {
                        "name": w.item_name, "windows": 0,
                        "best_diff": -999, "best_profit_rate": 0,
                    }
                item_summary[w.item_id]["windows"] += 1
                if w.avg_diff and w.avg_diff > item_summary[w.item_id]["best_diff"]:
                    item_summary[w.item_id]["best_diff"] = w.avg_diff
                if w.avg_profit_rate and w.avg_profit_rate > item_summary[w.item_id]["best_profit_rate"]:
                    item_summary[w.item_id]["best_profit_rate"] = w.avg_profit_rate

            rows = []
            for item_id, info in sorted(item_summary.items(),
                                         key=lambda x: -x[1]["best_diff"]):
                rows.append({
                    "饰品名称": info["name"],
                    "目标窗口数": info["windows"],
                    "最佳均价差(¥)": f"¥{info['best_diff']:+.2f}",
                    "最佳利润率": f"{info['best_profit_rate']*100:.2f}%",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            # 窗口明细
            with st.expander("查看目标窗口明细"):
                detail_rows = []
                for w in sorted(target_windows, key=lambda w: -(w.avg_diff or 0)):
                    detail_rows.append({
                        "饰品": w.item_name,
                        "窗口": f"{w.window_start}~{w.window_end}",
                        "BUFF均价": f"¥{w.buff_avg_price:.2f}",
                        "Steam均价($)": f"${w.steam_avg_price_usd:.2f}" if w.steam_avg_price_usd else "N/A",
                        "Steam均价(¥)": f"¥{w.steam_avg_price_cny:.2f}" if w.steam_avg_price_cny else "N/A",
                        "均价差": f"¥{w.avg_diff:+.2f}" if w.avg_diff else "N/A",
                        "利润率": f"{w.avg_profit_rate*100:.2f}%" if w.avg_profit_rate else "N/A",
                    })
                st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, height=400)

            # 图表
            with st.expander("📈 BUFF vs Steam 价格对比图表"):
                chart_idx = 0
                seen_items = set()
                for w in sorted(target_windows, key=lambda w: -(w.avg_diff or 0)):
                    if w.item_id in seen_items:
                        continue
                    seen_items.add(w.item_id)
                    try:
                        import plotly.graph_objects as go
                        fig = go.Figure()
                        if w.buff_records:
                            fig.add_trace(go.Scatter(
                                x=[r.date for r in w.buff_records],
                                y=[r.price for r in w.buff_records],
                                name=f"{w.item_name} BUFF(¥)",
                                mode="lines+markers",
                            ))
                        if w.steam_records:
                            fig.add_trace(go.Scatter(
                                x=[r.date for r in w.steam_records],
                                y=[r.price * _disp_rate for r in w.steam_records],
                                name=f"{w.item_name} Steam→¥",
                                mode="lines+markers",
                            ))
                        fig.update_layout(
                            title=f"{w.item_name} 价格对比 (1 USD = {_disp_rate} CNY)",
                            xaxis_title="日期", yaxis_title="价格 (¥)",
                            hovermode="x unified",
                        )
                        st.plotly_chart(fig, use_container_width=True,
                                        key=f"chart_{chart_idx}")
                        chart_idx += 1
                    except ImportError:
                        st.info("安装 plotly 可查看价格对比图表：pip install plotly")
                        break

            # 导出Excel
            st.divider()
            st.subheader("导出Excel报表")
            filepath = export_to_excel(target_windows, conversion_rate)
            st.success(f"Excel 已导出: {filepath}")

        _show_error_log()
        st.divider()
        if st.button("🔄 重新开始（清除所有结果）", use_container_width=True):
            for k in defaults:
                st.session_state[k] = defaults[k]
            st.rerun()

    # =====================================================================
    # 未完成 → 一键执行 + 分步执行
    # =====================================================================
    else:
        # ---- 进度指示 ----
        stage_names = ["滑动窗口筛选", "Steam市场数据获取", "比价筛选", "导出Excel"]
        done_count = sum([
            st.session_state.stage1_done,
            st.session_state.stage2_done,
            st.session_state.stage3_done,
            st.session_state.stage4_done,
        ])
        st.caption(f"当前进度：{done_count}/4  —  {stage_names[done_count] if done_count < 4 else '全部完成'}")

        # ---- 一键执行 ----
        if st.button("一键执行全部", type="primary", use_container_width=True,
                      help="自动依次执行第一二步→第三步→第四步，完成后可导出Excel"):
            st.session_state.one_click_mode = "running"
            st.session_state.error_log = []
            st.session_state.failed_step3_items = []
            # Reset
            st.session_state.stage1_done = False
            st.session_state.stage2_done = False
            st.session_state.stage3_done = False
            st.session_state.stage4_done = False
            st.session_state.export_path = ""
            _snapshot_params()

            # --- Step 1+2 ---
            with st.status("Step 1/3: BUFF获取 → 滑动窗口筛选…", expanded=True) as status:
                category_values = [config.CATEGORY_OPTIONS[n] for n in category_names if n != "全部/不限"]
                st.write("### 正在从 BUFF 市场抓取饰品列表…")
                try:
                    items = get_items_on_date(
                        today, target_count=target_count,
                        categories=category_values, min_price=20.0, min_volume=100)
                except Exception as e:
                    _log_error(1, "", "全部", f"BUFF列表获取异常: {e}")
                    items = []
                filtered = apply_initial_filters(items)
                st.session_state.items_from_buff = filtered
                st.write(f"BUFF 原始获取：{len(items)} 条 → 初步过滤：{len(filtered)} 条")

                all_windows = []
                if filtered:
                    st.write(f"### 正在对 {len(filtered)} 个饰品扫描滑动窗口…")
                    for i, item in enumerate(filtered):
                        st.write(f"  [{i+1}/{len(filtered)}] 扫描 {item.name}…")
                        start_date = today - timedelta(days=lookback_days)
                        history = get_price_history(item.item_id, start_date, today)
                        if history:
                            windows = find_stable_windows(
                                item.item_id, item.name, history,
                                window_days=stable_days, threshold=volatility_threshold,
                                min_price=20.0,
                            )
                            all_windows.extend(windows)
                            if windows:
                                st.write(f"    → {len(windows)} 个合格窗口")
                        else:
                            _log_error(1, item.item_id, item.name, "BUFF价格历史为空")
                        if i < len(filtered) - 1:
                            sleep_random(0.5, 1.0)

                st.session_state.qualifying_windows = all_windows
                items_with_windows = len(set(w.item_id for w in all_windows))
                st.write(f"---")
                st.write(f"**扫描完成：** {items_with_windows} 个饰品产生 {len(all_windows)} 个合格窗口")
                status.update(label=f"✅ Step 1+2: 滑动窗口筛选 — {len(all_windows)} 个窗口", state="complete")

            # --- Step 3 ---
            with st.status("Step 2/3: Steam市场数据获取…", expanded=True) as status:
                if all_windows:
                    steam_data_by_item = {}
                    # 按 item_id 汇总所有 BUFF 日期
                    item_buff_dates = {}
                    for w in all_windows:
                        item_buff_dates.setdefault(w.item_id, set())
                        for rec in w.buff_records:
                            item_buff_dates[w.item_id].add(rec.date)

                    unique_items = list(item_buff_dates.keys())
                    st.write(f"### 正在获取 {len(unique_items)} 个饰品的 Steam 市场数据…")

                    # 按皮系名分组（批处理优化）
                    items_map = {}
                    for w in all_windows:
                        if w.item_id not in items_map:
                            items_map[w.item_id] = w.item_name

                    # 构造 group_members 结构
                    class _Item:
                        def __init__(self, item_id, name):
                            self.item_id = item_id
                            self.name = name
                            self.price_history = []

                    _fake_items = [_Item(iid, items_map[iid]) for iid in unique_items]
                    groups = _steam.group_by_skin_name(_fake_items)
                    group_idx = 0

                    for base_name, group_items in groups.items():
                        group_idx += 1
                        st.write(f"  [{group_idx}/{len(groups)}] 皮肤组: {base_name} ({len(group_items)} 个变体)")

                        group_members = []
                        for gi in group_items:
                            target_dates = sorted(set(
                                d - timedelta(days=7) for d in item_buff_dates[gi.item_id]
                            ))
                            group_members.append({
                                "item_id": gi.item_id,
                                "buff_item_name": gi.name,
                                "target_dates": target_dates,
                                "base_skin_name": base_name,
                            })

                        batch_results = _steam.get_steam_market_data_batch(
                            representative_item_id=group_items[0].item_id,
                            group_members=group_members,
                        )

                        for member in group_members:
                            data = batch_results.get(member["item_id"])
                            if data and data.get("steam_price_history"):
                                steam_data_by_item[member["item_id"]] = data
                                st.write(f"    ✅ {member['buff_item_name']}: Steam 数据获取成功")
                            else:
                                reason = _steam.get_last_steam_error(item_id=member["item_id"]) or "获取失败"
                                ctx = _steam.get_last_steam_error_context(item_id=member["item_id"])
                                _log_error(2, member["item_id"], member["buff_item_name"], reason, context=ctx)
                                st.write(f"    ❌ {member['buff_item_name']}: {reason}")
                                st.session_state.failed_step3_items.append(member)

                        if group_idx < len(groups):
                            sleep_random(2.0, 3.0)

                    # 分发 Steam 数据到各窗口
                    for w in all_windows:
                        steam_data = steam_data_by_item.get(w.item_id)
                        if not steam_data or not steam_data.get("steam_price_history"):
                            continue
                        steam_history = steam_data["steam_price_history"]
                        steam_by_buff_date = {}
                        for sr in steam_history:
                            steam_by_buff_date[sr.date + timedelta(days=7)] = sr
                        matched_steam = []
                        for rec in w.buff_records:
                            sr = steam_by_buff_date.get(rec.date)
                            if sr:
                                matched_steam.append(sr)
                        if matched_steam:
                            w.steam_records = matched_steam
                            w.steam_avg_price_usd = sum(r.price for r in matched_steam) / len(matched_steam)

                    st.session_state.steam_data_by_item = steam_data_by_item
                    windows_with_steam = len([w for w in all_windows if w.steam_avg_price_usd is not None])
                    st.write(f"---")
                    st.write(f"**Steam 数据获取完成：** {windows_with_steam}/{len(all_windows)} 个窗口有数据")
                    status.update(label=f"✅ Step 2/3: Steam数据 — {windows_with_steam}/{len(all_windows)} 个窗口", state="complete")
                else:
                    st.write("无合格窗口，跳过 Steam 数据获取")
                    status.update(label="⏭️ Step 2/3: 无合格窗口", state="complete")

            # --- Step 4 ---
            with st.status("Step 3/3: 比价筛选…", expanded=True) as status:
                st.write(f"### 正在计算 BUFF vs Steam 价差…")
                st.write(f"**汇率:** 1 USD = {conversion_rate} CNY")
                st.write(f"**规则:** BUFF均价 > Steam均价(¥) → 目标窗口")
                st.write(f"---")

                for w in all_windows:
                    if w.steam_avg_price_usd is None:
                        continue
                    w.steam_avg_price_cny = w.steam_avg_price_usd * conversion_rate
                    w.avg_diff = w.buff_avg_price - w.steam_avg_price_cny
                    if w.steam_avg_price_cny > 0:
                        w.avg_profit_rate = w.avg_diff / w.steam_avg_price_cny
                    w.is_target = w.avg_diff > 0
                    steam_by_buff = {}
                    for sr in w.steam_records:
                        steam_by_buff[sr.date + timedelta(days=7)] = sr
                    for rec in w.buff_records:
                        sr = steam_by_buff.get(rec.date)
                        w.date_pairs.append({
                            "buff_date": rec.date,
                            "buff_price": rec.price,
                            "steam_date": sr.date if sr else None,
                            "steam_price_usd": sr.price if sr else None,
                            "steam_price_cny": (sr.price * conversion_rate) if sr else None,
                            "diff": (rec.price - sr.price * conversion_rate) if sr else None,
                        })

                target_count = sum(1 for w in all_windows if w.is_target)
                st.write(f"**比价完成：** {len(all_windows)} 个窗口，{target_count} 个目标窗口")
                status.update(label=f"✅ Step 3/3: 比价筛选 — {target_count} 个目标窗口", state="complete")

            st.session_state.stage1_done = True
            st.session_state.stage2_done = True
            st.session_state.stage3_done = True
            st.session_state.stage4_done = True
            st.session_state._run_conversion_rate = conversion_rate
            st.session_state.one_click_mode = "done"
            st.rerun()

        # ====================================================================
        # 分步执行
        # ====================================================================
        st.divider()
        with st.expander("⚙️ 分步执行", expanded=False):
            # =====================================================================
            # 第一、二步（合并）：BUFF抓取 + 滑动窗口筛选
            # =====================================================================
            st.subheader("第一、二步：滑动窗口筛选")
            st.caption(
                f"从BUFF抓取当前在售饰品 → 拉取近 {lookback_days} 天价格历史 → "
                f"以 {stable_days} 天为窗口滑动扫描 → 记录所有稳定窗口。"
            )

            btn_label = "执行第一、二步" if not st.session_state.stage1_done else "重新执行第一、二步"
            if st.button(btn_label, type="primary", use_container_width=True):
                st.session_state.stage1_done = False
                st.session_state.stage2_done = False
                st.session_state.stage3_done = False
                st.session_state.stage4_done = False
                st.session_state.export_path = ""
                st.session_state.error_log = []
                st.session_state.failed_step3_items = []
                st.session_state.one_click_mode = None
                _snapshot_params()

                try:
                    items = get_items_on_date(today, target_count=target_count)
                except Exception as e:
                    _log_error(1, "", "全部", f"BUFF列表获取异常: {e}")
                    items = []
                filtered = apply_initial_filters(items)
                st.session_state.items_from_buff = filtered
                st.info(f"BUFF 原始获取：{len(items)} 条 → 初步过滤：{len(filtered)} 条")

                if filtered:
                    all_windows = []
                    progress_bar = st.progress(0, text="正在扫描滑动窗口...")
                    for i, item in enumerate(filtered):
                        progress_bar.progress(
                            (i + 1) / len(filtered),
                            text=f"[{i+1}/{len(filtered)}] 扫描 {item.name}",
                        )
                        start_date = today - timedelta(days=lookback_days)
                        history = get_price_history(item.item_id, start_date, today)
                        if history:
                            windows = find_stable_windows(
                                item.item_id, item.name, history,
                                window_days=stable_days,
                                threshold=volatility_threshold,
                                min_price=20.0,
                            )
                            all_windows.extend(windows)
                        else:
                            _log_error(1, item.item_id, item.name, "BUFF价格历史为空")
                        if i < len(filtered) - 1:
                            sleep_random(0.5, 1.0)
                    progress_bar.empty()

                    st.session_state.qualifying_windows = all_windows
                    items_with_windows = len(set(w.item_id for w in all_windows))
                    st.success(f"扫描完成：{items_with_windows} 个饰品产生 {len(all_windows)} 个合格窗口")
                else:
                    st.warning("没有饰品通过初步筛选，请检查数据。")

                st.session_state.stage1_done = True
                st.rerun()

            if st.session_state.stage1_done:
                windows = st.session_state.qualifying_windows
                filtered = st.session_state.items_from_buff

                if not windows:
                    st.warning("没有找到任何合格窗口，请放宽阈值或增加回溯天数后重试。")
                else:
                    st.subheader("合格窗口汇总")
                    item_summary = {}
                    for w in windows:
                        item_summary.setdefault(w.item_id, {
                            "name": w.item_name, "window_count": 0,
                            "best_volatility": 999, "latest_start": None,
                        })
                        item_summary[w.item_id]["window_count"] += 1
                        item_summary[w.item_id]["best_volatility"] = min(
                            item_summary[w.item_id]["best_volatility"], w.volatility)
                        if (item_summary[w.item_id]["latest_start"] is None
                                or w.window_start > item_summary[w.item_id]["latest_start"]):
                            item_summary[w.item_id]["latest_start"] = w.window_start

                    rows = []
                    for item_id, info in sorted(item_summary.items(), key=lambda x: -x[1]["window_count"]):
                        rows.append({
                            "饰品名称": info["name"], "合格窗口数": info["window_count"],
                            "最佳波动率": f"{info['best_volatility']*100:.2f}%",
                            "最近窗口": info["latest_start"],
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

                    # 逐步诊断
                    if filtered:
                        with st.expander("🔍 逐步诊断：选择单个饰品检查价格提取流程"):
                            st.markdown("选中一个饰品后点击按钮，逐步展示价格提取的每一步。")
                            col_a, col_b = st.columns([2, 1])
                            with col_a:
                                test_idx = st.selectbox(
                                    "选择饰品", range(len(filtered)),
                                    format_func=lambda i: f"{filtered[i].name} (ID:{filtered[i].item_id})",
                                    key="diag_select"
                                )
                            with col_b:
                                run_diag = st.button("🔬 开始诊断", type="primary", use_container_width=True)

                            if run_diag:
                                item = filtered[test_idx]
                                start = today - timedelta(days=lookback_days)
                                with st.spinner("正在诊断价格提取..."):
                                    diag = diagnose_price_extraction(item.item_id, start, today)
                                st.divider()
                                st.markdown(f"### 诊断结果：{item.name}")
                                ok_count = sum(1 for s in diag["steps"] if s["ok"])
                                total = len(diag["steps"])
                                if ok_count == total:
                                    st.success(f"全部 {total} 步通过！")
                                else:
                                    st.error(f"{ok_count}/{total} 步通过")
                                for step in diag["steps"]:
                                    icon = "✅" if step["ok"] else "❌"
                                    with st.expander(f"{icon} {step['name']} — {step['detail'][:80]}",
                                                     expanded=not step["ok"]):
                                        st.text(step["detail"])

                    with st.expander("查看所有合格窗口明细"):
                        detail_rows = []
                        for w in sorted(windows, key=lambda w: (w.item_name, w.window_start)):
                            detail_rows.append({
                                "饰品名称": w.item_name, "窗口起始": w.window_start,
                                "窗口结束": w.window_end, "BUFF均价": f"{w.buff_avg_price:.2f}",
                                "BUFF最低": f"{w.buff_min_price:.2f}", "BUFF最高": f"{w.buff_max_price:.2f}",
                                "波动率": f"{w.volatility*100:.2f}%",
                            })
                        st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, height=400)

            st.divider()

            # =====================================================================
            # 第三步：Steam市场数据
            # =====================================================================
            st.subheader("第三步：Steam市场数据获取")
            st.caption(
                "对每个有合格窗口的饰品，汇总所有窗口涉及的 BUFF 日期，"
                "统一查询 Steam 市场数据（Steam日期 = BUFF日期 − 7天），再将数据分发回各窗口。"
                "按皮肤名分组批处理，同组共用一个 Steam 页面。"
            )

            if st.session_state.stage1_done and st.session_state.qualifying_windows:
                step3_disabled = st.session_state.stage2_done
                if st.button("执行第三步", type="primary", disabled=step3_disabled, use_container_width=True):
                    windows = st.session_state.qualifying_windows
                    steam_data_by_item = {}
                    st.session_state.failed_step3_items = []

                    item_buff_dates = {}
                    for w in windows:
                        item_buff_dates.setdefault(w.item_id, set())
                        for rec in w.buff_records:
                            item_buff_dates[w.item_id].add(rec.date)

                    unique_items = list(item_buff_dates.keys())

                    # 已按皮系名分组
                    class _Item:
                        def __init__(self, iid, name):
                            self.item_id = iid; self.name = name
                    _fake_items = [_Item(iid, next((w.item_name for w in windows if w.item_id == iid), iid)) for iid in unique_items]
                    groups = _steam.group_by_skin_name(_fake_items)

                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    group_count = len(groups)
                    group_idx = 0

                    for base_name, group_items in groups.items():
                        group_idx += 1
                        status_text.text(f"[{group_idx}/{group_count}] 组: {base_name}")

                        group_members = []
                        for gi in group_items:
                            target_dates = sorted(set(
                                d - timedelta(days=7) for d in item_buff_dates[gi.item_id]
                            ))
                            group_members.append({
                                "item_id": gi.item_id,
                                "buff_item_name": gi.name,
                                "target_dates": target_dates,
                                "base_skin_name": base_name,
                            })

                        batch_results = _steam.get_steam_market_data_batch(
                            representative_item_id=group_items[0].item_id,
                            group_members=group_members,
                        )

                        for member in group_members:
                            data = batch_results.get(member["item_id"])
                            if data and data.get("steam_price_history"):
                                steam_data_by_item[member["item_id"]] = data
                            else:
                                reason = _steam.get_last_steam_error(item_id=member["item_id"]) or "获取失败"
                                _log_error(2, member["item_id"], member["buff_item_name"], reason)
                                st.session_state.failed_step3_items.append(member)

                        progress_bar.progress(group_idx / group_count)
                        if group_idx < group_count:
                            sleep_random(2.0, 3.0)

                    progress_bar.empty()
                    status_text.empty()

                    # 分发到各窗口
                    for w in windows:
                        steam_data = steam_data_by_item.get(w.item_id)
                        if not steam_data or not steam_data.get("steam_price_history"):
                            continue
                        steam_history = steam_data["steam_price_history"]
                        steam_by_buff_date = {}
                        for sr in steam_history:
                            steam_by_buff_date[sr.date + timedelta(days=7)] = sr
                        matched_steam = []
                        for rec in w.buff_records:
                            sr = steam_by_buff_date.get(rec.date)
                            if sr:
                                matched_steam.append(sr)
                        if matched_steam:
                            w.steam_records = matched_steam
                            w.steam_avg_price_usd = sum(r.price for r in matched_steam) / len(matched_steam)

                    st.session_state.steam_data_by_item = steam_data_by_item
                    st.session_state.stage2_done = True
                    st.session_state.stage3_done = False
                    st.session_state.stage4_done = False
                    st.session_state.export_path = ""
                    st.rerun()

            if st.session_state.stage2_done:
                windows = st.session_state.qualifying_windows
                windows_with_steam = [w for w in windows if w.steam_avg_price_usd is not None]
                st.success(f"Steam数据获取完成：{len(windows_with_steam)}/{len(windows)} 个窗口获取到Steam数据")

                # 重试失败饰品
                _failed = st.session_state.get("failed_step3_items", [])
                if _failed:
                    with st.expander(f"🔄 重试失败饰品（{len(_failed)} 条）", expanded=False):
                        for fi in _failed:
                            col_a, col_b = st.columns([4, 1])
                            with col_a:
                                st.caption(f"{fi['buff_item_name']}  (ID: {fi['item_id']})")
                            with col_b:
                                if st.button("重试", key=f"step3_retry_{fi['item_id']}", use_container_width=True):
                                    with st.spinner(f"正在重试 {fi['buff_item_name']}..."):
                                        result = _steam.get_steam_market_data(
                                            fi["item_id"], fi["target_dates"], fi["buff_item_name"],
                                        )
                                    if result:
                                        st.session_state.steam_data_by_item[fi["item_id"]] = result
                                        st.success(f"✅ 重试成功")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ 重试失败: {_steam.get_last_steam_error()}")

                        if st.button("🔄 重试全部", type="primary", key="step3_retry_all", use_container_width=True):
                            with st.spinner(f"正在批量重试 {len(_failed)} 个失败饰品..."):
                                batch_result = _steam.retry_steam_failed_items(_failed)
                            ok = 0
                            for fi in _failed:
                                data = batch_result.get(fi["item_id"])
                                if data:
                                    st.session_state.steam_data_by_item[fi["item_id"]] = data
                                    ok += 1
                            if ok == len(_failed):
                                st.success(f"✅ 全部重试成功: {ok}/{len(_failed)}")
                            elif ok > 0:
                                st.warning(f"部分重试成功: {ok}/{len(_failed)}，剩余 {len(_failed)-ok} 条仍失败")
                            else:
                                st.error(f"全部重试失败: 0/{len(_failed)}，请检查代理或Steam登录状态")
                            st.rerun()

                # Steam 诊断
                if windows_with_steam:
                    with st.expander("🔍 逐步诊断：Steam数据提取流程"):
                        col_a, col_b = st.columns([2, 1])
                        with col_a:
                            diag_idx = st.selectbox(
                                "选择饰品",
                                range(len(windows_with_steam)),
                                format_func=lambda i: f"{windows_with_steam[i].item_name} (ID:{windows_with_steam[i].item_id})",
                                key="steam_diag_select"
                            )
                        with col_b:
                            run_steam_diag = st.button("🔬 开始诊断", type="primary", use_container_width=True)

                        if run_steam_diag:
                            w = windows_with_steam[diag_idx]
                            target_dates = sorted(set(
                                r.date - timedelta(days=7) for r in w.buff_records
                            ))
                            with st.spinner("正在诊断 Steam 数据提取..."):
                                diag = diagnose_steam_extraction(w.item_id, target_dates, w.item_name)
                            st.divider()
                            st.markdown(f"### Steam诊断：{w.item_name}")
                            ok_count = sum(1 for s in diag["steps"] if s["ok"])
                            total = len(diag["steps"])
                            if ok_count == total:
                                st.success(f"全部 {total} 步通过！")
                            else:
                                st.error(f"{ok_count}/{total} 步通过")
                            for step in diag["steps"]:
                                icon = "✅" if step["ok"] else "❌"
                                with st.expander(f"{icon} {step['name']} — {step['detail'][:80]}",
                                                 expanded=not step["ok"]):
                                    st.text(step["detail"])

                with st.expander("查看Steam数据明细"):
                    rows = []
                    for w in sorted(windows, key=lambda w: (w.item_name, w.window_start)):
                        rows.append({
                            "饰品名称": w.item_name, "窗口起始": w.window_start,
                            "窗口结束": w.window_end, "BUFF均价": f"{w.buff_avg_price:.2f}",
                            "Steam均价($)": f"${w.steam_avg_price_usd:.2f}" if w.steam_avg_price_usd else "N/A",
                            "Steam数据点数": len(w.steam_records),
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

            st.divider()

            # =====================================================================
            # 第四步：比价筛选
            # =====================================================================
            st.subheader("第四步：比价筛选")
            st.caption(
                f"按窗口计算：Steam均价(¥) = Steam均价($) × {conversion_rate}，"
                f"均价差 = BUFF均价 − Steam均价(¥)。筛选均价差 > 0 的窗口。"
            )

            if st.session_state.stage2_done:
                step4_disabled = st.session_state.stage3_done
                if st.button("执行第四步", type="primary", disabled=step4_disabled, use_container_width=True):
                    windows = st.session_state.qualifying_windows
                    for w in windows:
                        if w.steam_avg_price_usd is None:
                            continue
                        w.steam_avg_price_cny = w.steam_avg_price_usd * conversion_rate
                        w.avg_diff = w.buff_avg_price - w.steam_avg_price_cny
                        if w.steam_avg_price_cny > 0:
                            w.avg_profit_rate = w.avg_diff / w.steam_avg_price_cny
                        w.is_target = w.avg_diff > 0
                        steam_by_buff = {}
                        for sr in w.steam_records:
                            steam_by_buff[sr.date + timedelta(days=7)] = sr
                        for rec in w.buff_records:
                            sr = steam_by_buff.get(rec.date)
                            w.date_pairs.append({
                                "buff_date": rec.date,
                                "buff_price": rec.price,
                                "steam_date": sr.date if sr else None,
                                "steam_price_usd": sr.price if sr else None,
                                "steam_price_cny": (sr.price * conversion_rate) if sr else None,
                                "diff": (rec.price - sr.price * conversion_rate) if sr else None,
                            })
                    st.session_state.stage3_done = True
                    st.session_state.stage4_done = False
                    st.session_state._run_conversion_rate = conversion_rate
                    st.rerun()

            if st.session_state.stage3_done:
                windows = st.session_state.qualifying_windows
                target_windows = [w for w in windows if w.is_target]
                windows_with_data = [w for w in windows if w.steam_avg_price_usd is not None]

                st.success(
                    f"比价完成：{len(windows_with_data)} 个窗口有对比数据，"
                    f"其中 **{len(target_windows)} 个目标窗口**（均价差>0）"
                )

                if windows_with_data:
                    rows = []
                    for w in sorted(windows_with_data, key=lambda w: -(w.avg_diff or 0)):
                        rows.append({
                            "饰品名称": w.item_name, "窗口起始": w.window_start,
                            "窗口结束": w.window_end, "BUFF均价(¥)": f"{w.buff_avg_price:.2f}",
                            "Steam均价($)": f"${w.steam_avg_price_usd:.2f}",
                            "Steam均价(¥)": f"¥{w.steam_avg_price_cny:.2f}",
                            "均价差(¥)": f"¥{w.avg_diff:+.2f}",
                            "利润率": f"{w.avg_profit_rate*100:.2f}%" if w.avg_profit_rate else "N/A",
                            "判定": "目标" if w.is_target else "未达标",
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

                    # 图表
                    with st.expander("📈 BUFF vs Steam 价格对比图表"):
                        chart_idx = 0
                        seen_items = set()
                        for w in sorted(windows_with_data, key=lambda w: -(w.avg_diff or 0)):
                            if w.item_id in seen_items:
                                continue
                            seen_items.add(w.item_id)
                            try:
                                import plotly.graph_objects as go
                                fig = go.Figure()
                                if w.buff_records:
                                    fig.add_trace(go.Scatter(
                                        x=[r.date for r in w.buff_records],
                                        y=[r.price for r in w.buff_records],
                                        name=f"{w.item_name} BUFF(¥)", mode="lines+markers",
                                    ))
                                if w.steam_records:
                                    fig.add_trace(go.Scatter(
                                        x=[r.date for r in w.steam_records],
                                        y=[r.price * conversion_rate for r in w.steam_records],
                                        name=f"{w.item_name} Steam→¥", mode="lines+markers",
                                    ))
                                title_suffix = " 🎯目标" if w.is_target else ""
                                fig.update_layout(
                                    title=f"{w.item_name} 价格对比 (1 USD = {conversion_rate} CNY){title_suffix}",
                                    xaxis_title="日期", yaxis_title="价格 (¥)", hovermode="x unified",
                                )
                                st.plotly_chart(fig, use_container_width=True, key=f"step4_chart_{chart_idx}")
                                chart_idx += 1
                            except ImportError:
                                st.info("安装 plotly 可查看图表：pip install plotly")
                                break

                    with st.expander("按饰品查看详细配对"):
                        seen_items = set()
                        for w in sorted(windows_with_data, key=lambda w: -(w.avg_diff or 0)):
                            if w.item_name in seen_items:
                                continue
                            seen_items.add(w.item_name)
                            st.markdown(f"**{w.item_name}** — "
                                        f"{len([x for x in windows_with_data if x.item_id == w.item_id])} 个窗口")
                            item_windows = [x for x in windows_with_data if x.item_id == w.item_id]
                            pair_rows = []
                            for iw in item_windows:
                                pair_rows.append({
                                    "窗口": f"{iw.window_start} ~ {iw.window_end}",
                                    "BUFF均价": f"¥{iw.buff_avg_price:.2f}",
                                    "Steam均价($)": f"${iw.steam_avg_price_usd:.2f}",
                                    "Steam均价(¥)": f"¥{iw.steam_avg_price_cny:.2f}",
                                    "均价差": f"¥{iw.avg_diff:+.2f}",
                                    "利润率": f"{iw.avg_profit_rate*100:.2f}%" if iw.avg_profit_rate else "N/A",
                                })
                            st.dataframe(pd.DataFrame(pair_rows), use_container_width=True)
                            st.divider()

            st.divider()

            # =====================================================================
            # Excel 导出
            # =====================================================================
            if st.session_state.stage3_done:
                st.subheader("导出Excel报表")
                st.caption("仅导出目标饰品（均价差>0），按时间点逐行列出每次提取的 BUFF/Steam 价格。")

                col_exp, col_reset = st.columns([1, 3])
                with col_exp:
                    if st.button("导出Excel", type="primary", use_container_width=True):
                        windows = st.session_state.qualifying_windows
                        target_windows = [w for w in windows if w.is_target]
                        if not target_windows:
                            st.warning("没有目标饰品可导出。")
                        else:
                            filepath = export_to_excel(target_windows, conversion_rate)
                            st.session_state.stage4_done = True
                            st.session_state.export_path = filepath
                            st.success(f"Excel已导出到: {filepath}")
                            st.rerun()

                if st.session_state.stage4_done and st.session_state.export_path:
                    st.info(f"上次导出文件: {st.session_state.export_path}")

                with col_reset:
                    if st.button("重新开始（清除所有结果）", use_container_width=True):
                        for k in defaults:
                            st.session_state[k] = defaults[k]
                        st.rerun()

        # ---- 分步模式错误日志 ----
        if any([st.session_state.stage1_done, st.session_state.stage2_done,
                st.session_state.stage3_done]):
            _show_error_log()

with tabs[1]:
    st.subheader("BUFF价格走势查询")

    col1, col2 = st.columns([2, 1])
    with col1:
        item_id_input = st.text_input(
            "请输入饰品ID（可从BUFF商品链接中获取）",
            value="",
            key="buff_price_trend_item_id",
        )
    with col2:
        time_range = st.selectbox(
            "日期范围",
            options=["最近3个月", "最近6个月", "最近1年"],
            index=0,
            key="buff_price_trend_time_range",
        )

    if st.button("查询BUFF价格走势", type="primary", key="query_buff_price_trend"):
        if not item_id_input.strip():
            st.warning("请输入饰品ID")
        else:
            with st.spinner("正在从BUFF获取价格走势数据..."):
                history_data = get_full_price_history(item_id_input.strip(), time_range)

            if not history_data:
                st.error("未能获取到价格走势数据，请检查饰品ID是否正确或BUFF登录状态。")
            else:
                st.success(f"成功获取 {len(history_data)} 条曲线数据")

                try:
                    import plotly.graph_objects as go
                    fig = go.Figure()

                    preferred_order = [
                        "在售最低", "求购最高", "在售数量", "成交记录", "买卖点", "存世量",
                    ]
                    sorted_names = []
                    for name in preferred_order:
                        if name in history_data:
                            sorted_names.append(name)
                    for name in history_data:
                        if name not in sorted_names:
                            sorted_names.append(name)

                    for name in sorted_names:
                        data = history_data[name]
                        dates = [r[0] for r in data]
                        values = [r[1] for r in data]
                        visible = True if name == "在售最低" else "legendonly"

                        fig.add_trace(
                            go.Scatter(
                                x=dates, y=values, name=name,
                                mode="lines", visible=visible,
                                hovertemplate=f"{name}: %{{y:.2f}}<extra></extra>",
                            )
                        )

                    fig.update_layout(
                        hovermode="x unified",
                        xaxis_title="日期",
                        yaxis_title="价格",
                        legend=dict(
                            orientation="h", yanchor="bottom",
                            y=1.02, xanchor="center", x=0.5,
                        ),
                        margin=dict(t=80),
                    )

                    st.plotly_chart(fig, use_container_width=True, key="buff_price_trend_chart")
                except ImportError:
                    st.error("请安装 plotly 以查看交互式图表：pip install plotly")
