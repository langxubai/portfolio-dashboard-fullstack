import streamlit as st
import pandas as pd
import plotly.express as px
from api_client import api

st.set_page_config(
    page_title="Personal Finance Dashboard",
    page_icon="💹",
    layout="wide",
)


@st.cache_data(ttl=30, show_spinner=False)
def load_positions():
    return api.get_positions()


@st.cache_data(ttl=60, show_spinner=False)
def load_exchange_rates(base, targets):
    return api.get_exchange_rates(base=base, targets=list(targets))


@st.cache_data(ttl=300, show_spinner=False)
def load_history(period, base_currency):
    return api.get_portfolio_history(
        period=period,
        base_currency=base_currency,
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_accounts():
    return api.get_accounts()


@st.cache_data(ttl=60, show_spinner=False)
def load_market_status():
    return api.get_market_status()


def display_time(value):
    if not value:
        return "未记录"
    if len(str(value)) == 10:
        return str(value)
    try:
        return pd.Timestamp(value).tz_convert("Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(value)

st.title("💹 Personal Finance Dashboard")

if st.button("刷新最新价格", help="向行情源查询最新报价、基金净值和汇率", disabled=st.session_state.get("refresh_running", False)):
    try:
        report = api.refresh_market()
        st.session_state["refresh_running"] = report["status"] == "running"
        st.session_state["refresh_report"] = report
        st.session_state["refresh_poll_errors"] = 0
        st.cache_data.clear()
        st.rerun()
    except Exception as exc:
        st.error(f"无法发起行情更新：{exc}")


@st.fragment(run_every=2 if st.session_state.get("refresh_running") else None)
def refresh_progress():
    if st.session_state.get("refresh_running"):
        try:
            report = api.get_refresh_status()
            st.session_state["refresh_poll_errors"] = 0
            if report["status"] != "running":
                st.session_state["refresh_running"] = False
                st.session_state["refresh_report"] = report
                st.cache_data.clear()
                st.rerun()
            st.info("正在查询最新行情，各数据源独立更新……")
        except Exception as exc:
            st.session_state["refresh_poll_errors"] = st.session_state.get("refresh_poll_errors", 0) + 1
            st.warning(f"暂时无法读取更新进度：{exc}")
            if st.session_state["refresh_poll_errors"] >= 3:
                st.session_state["refresh_running"] = False
                st.session_state["refresh_report"] = {"status": "unknown"}
                st.rerun()
    else:
        report = st.session_state.get("refresh_report", {})
        if report.get("status") == "completed":
            st.success(f"最新行情查询完成，{report.get('succeeded', 0)} 项读取成功（含汇率）。")
        elif report.get("status") in {"partial", "failed"}:
            st.warning(f"本次查询 {report.get('succeeded', 0)} 项成功，{report.get('failed', 0)} 项失败。失败项目继续显示上次成功的价格。")
            with st.expander("查看本次更新失败的项目"):
                st.dataframe(pd.DataFrame([
                    {"项目": item["symbol"], "原因": item.get("error")}
                    for item in report.get("results", []) if not item["ok"]
                ]), hide_index=True)
        elif report.get("status") in {"idle", "unknown"}:
            st.warning("本次更新结果暂时无法确认，可以重新点击刷新。")


refresh_progress()

with st.spinner("Loading portfolio data..."):
    try:
        positions_data = load_positions()
    except Exception as e:
        st.error(f"Failed to connect to backend: {e}")
        st.info("Make sure FastAPI backend is running on the configured BACKEND_URL.")
        st.stop()

if not positions_data:
    st.info("No active positions found. Go to 'Transactions' to record a new trade.")
else:
    target_currencies = list(set([pos.get("currency", "CNY") for pos in positions_data]))
    
    col_tb1, col_tb2 = st.columns([3, 1])
    with col_tb1:
        st.subheader("📊 资产总览 (Portfolio Overview)")
    with col_tb2:
        base_currency = st.selectbox("基准货币 (Base)", ["CNY", "USD", "HKD", "EUR", "JPY", "GBP", "SGD"], index=0)
        
    with st.spinner("Fetching exchange rates..."):
        try:
            exchange_rates = load_exchange_rates(
                base_currency,
                tuple(sorted(target_currencies)),
            )
        except Exception as e:
            exchange_rates = {base_currency: 1.0}
            st.error(f"汇率快照读取失败：{e}")

    unavailable_positions = []
    stale_positions = []
    missing_fx = set()
        
    for pos in positions_data:
        pos_currency = pos.get("currency", "CNY")
        rate = exchange_rates.get(pos_currency)
        has_price = pos.get("current_value") is not None
        if rate is None:
            missing_fx.add(f"{pos_currency}/{base_currency}")

        valuation_available = has_price and rate is not None
        pos["valuation_available"] = valuation_available
        pos["converted_current_value"] = (
            float(pos["current_value"]) * rate if valuation_available else None
        )
        pos["converted_unrealized_pnl"] = (
            float(pos["unrealized_pnl"]) * rate
            if valuation_available and pos.get("unrealized_pnl") is not None
            else None
        )
        pos["converted_realized_pnl"] = (
            float(pos.get("realized_pnl") or 0.0) * rate
            if rate is not None
            else None
        )
        pos["converted_daily_pnl"] = (
            float(pos.get("daily_pnl") or 0.0) * rate
            if valuation_available
            else None
        )
        pos["converted_total_cost"] = (
            float(pos.get("average_cost") or 0.0)
            * float(pos.get("total_quantity") or 0.0)
            * rate
            if valuation_available
            else None
        )

        if not valuation_available:
            unavailable_positions.append(pos)
        elif pos.get("price_is_stale") or pos.get("price_status") == "stale":
            stale_positions.append(pos)

    if unavailable_positions or missing_fx:
        st.error(
            f"有 {len(unavailable_positions)} 个持仓缺少有效估值，"
            "已从总额中排除；不会按 0 计算。"
        )
        with st.expander("查看行情与汇率问题", expanded=True):
            if unavailable_positions:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "代码": pos["symbol"],
                                "名称": pos["name"],
                                "状态": pos.get("price_status"),
                                "数据源": pos.get("price_source"),
                                "错误": pos.get("price_error") or "无价格快照",
                            }
                            for pos in unavailable_positions
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )
            if missing_fx:
                st.warning("缺少汇率：" + ", ".join(sorted(missing_fx)))
    if stale_positions:
        st.warning(
            "正在使用过期行情："
            + ", ".join(pos["symbol"] for pos in stale_positions)
        )

    with st.expander("行情来源与更新时间"):
        st.caption("时间均为北京时间；仅显示日期的条目表示日线价格、基金净值或每日参考汇率。")
        try:
            market_status = load_market_status()
            if market_status.get("store_error"):
                st.warning(market_status["store_error"])
            fx = market_status.get("fx", [])
            if fx:
                st.dataframe(pd.DataFrame([
                    {"汇率": row["pair"], "来源": row.get("source"),
                     "价格类型": "每日参考汇率" if row.get("kind") == "reference_rate" else "日线价格",
                     "行情日期": display_time(row.get("as_of")),
                     "采集成功时间": display_time(row.get("fetched_at")),
                     "状态": row.get("status"), "错误": row.get("error")}
                    for row in fx if row["pair"].endswith("/" + base_currency)
                ]), hide_index=True)
            history_errors = [row for row in market_status.get("assets", []) if row.get("history_status") == "error"]
            if history_errors:
                st.warning("部分历史曲线尚未更新：" + ", ".join(row["symbol"] for row in history_errors))
        except Exception as exc:
            st.warning(f"无法读取行情状态：{exc}")

    # 1. Summarize metrics
    total_asset_value = sum(
        pos["converted_current_value"] or 0.0 for pos in positions_data
    )
    total_unrealized_pnl = sum(
        pos["converted_unrealized_pnl"] or 0.0 for pos in positions_data
    )
    total_realized_pnl = sum(
        pos["converted_realized_pnl"] or 0.0 for pos in positions_data
    )
    total_daily_pnl = sum(
        pos["converted_daily_pnl"] or 0.0 for pos in positions_data
    )
    missing_daily = [pos["name"] for pos in positions_data
                     if pos.get("current_price") is not None and pos.get("daily_pnl") is None
                     and pos.get("asset_type") != "Custom"]
    if missing_daily:
        st.caption("以下资产缺少前收盘价，今日收益暂未包含它们：" + "、".join(missing_daily))
    total_cost_basis = sum(
        pos["converted_total_cost"] or 0.0 for pos in positions_data
    )
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"总资产价值 ({base_currency})", f"{total_asset_value:,.2f}",
                delta=f"{total_daily_pnl:,.2f} 今日收益", delta_color="normal")
    col2.metric(f"未实现收益 ({base_currency})", f"{total_unrealized_pnl:,.2f}")
    
    if total_cost_basis > 0:
        total_pnl_percent = (total_unrealized_pnl / total_cost_basis) * 100
    else:
        total_pnl_percent = 0.0
    col3.metric("未实现收益率 (Unrealized %)", f"{total_pnl_percent:.2f}%")
    
    col4.metric(f"已实现总收益 ({base_currency})", f"{total_realized_pnl:,.2f}")
    if unavailable_positions:
        st.caption(
            f"以上估值不包含 {len(unavailable_positions)} 个缺少价格或汇率的持仓，"
            "不会将它们错误计为 0。"
        )

    st.markdown("---")

    # 2. Charts Section
    
    # 2.1 History Chart
    st.markdown("##### 📈 收益率曲线图 (Return Rate Curve)")
    period = st.selectbox("选择周期 (Select Period)", ["1mo", "3mo", "6mo", "1y", "3y", "10y", "ytd", "max"], index=3, format_func=lambda x: {"1mo": "1个月", "3mo": "3个月", "6mo": "6个月", "1y": "1年", "3y": "3年", "10y": "10年", "ytd": "今年以来", "max": "全部"}[x])
    with st.spinner("Loading history..."):
        try:
            history_data = load_history(period, base_currency)
            hist_list = history_data.get("history", [])
            history_warnings = history_data.get("warnings", [])
            if history_warnings:
                with st.expander(
                    f"历史数据警告 ({len(history_warnings)})",
                    expanded=False,
                ):
                    for warning in history_warnings:
                        st.warning(warning)
            if hist_list:
                hist_df = pd.DataFrame(hist_list)
                # create a sub-selectbox or radio for Total Value vs Return Rate
                chart_type = st.radio("图表类型 (Chart Type)", ["累计净值 (Total Value)", "累计收益率 (Return Rate %)"], horizontal=True)
                if "Return Rate" in chart_type:
                    hist_df["return_rate_pct"] = hist_df["return_rate"] * 100
                    fig_hist = px.line(hist_df, x="date", y="return_rate_pct", title="Portfolio Return Rate %")
                else:
                    fig_hist = px.line(hist_df, x="date", y="total_value", title="Portfolio Total Value")
                st.plotly_chart(fig_hist, width="stretch")
            else:
                st.info("尚无足够的历史来生成曲线图 (Not enough history to generate chart).")
        except Exception as e:
            st.error(f"Failed to load history: {e}")

    # Convert data for plotting
    df = pd.DataFrame(positions_data)
    # Extract asset info from flat structure and map accounts
    df["asset_name"] = df["name"]
    df["asset_symbol"] = df["symbol"]
    
    try:
        acc_list = load_accounts()
        acc_map = {a["id"]: a["name"] for a in acc_list}
    except Exception as e:
        st.warning(f"账户名称读取失败，将显示 UUID：{e}")
        acc_map = {}
    
    df["account_name"] = df["account_id"].apply(lambda x: acc_map.get(x, x))
    
    # Cast decimals strings to float for plotly
    df["current_value"] = pd.to_numeric(df["current_value"], errors="coerce")
    df["unrealized_pnl"] = pd.to_numeric(df["unrealized_pnl"], errors="coerce")
    df["realized_pnl"] = pd.to_numeric(df["realized_pnl"], errors="coerce")
    df["daily_pnl"] = pd.to_numeric(df["daily_pnl"], errors="coerce").fillna(0.0)
    
    is_held = df["total_quantity"].astype(float) > 0
    active_df = df[is_held & df["valuation_available"]]
    
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        # Pie Chart: Allocation by Asset Value
        if not active_df.empty:
            fig_pie = px.pie(active_df, values="converted_current_value", names="asset_name", 
                             title=f"资产分配 (Asset Allocation in {base_currency})", hole=0.3)
            st.plotly_chart(fig_pie, width="stretch")
        else:
            st.info("No active holdings for allocation chart.")
            
    with chart_col2:
        # Bar Chart: PNL by Asset
        if not active_df.empty:
            fig_bar = px.bar(active_df, x="asset_name", y="converted_unrealized_pnl", 
                             title=f"各资产未实现收益 (Unrealized PnL in {base_currency})",
                             color="converted_unrealized_pnl", color_continuous_scale="rdylgn")
            fig_bar.update_layout(xaxis_title=None)
            st.plotly_chart(fig_bar, width="stretch")
        
    st.markdown("---")
    
    # 3. Detailed Data Table
    heading, controls = st.columns([3, 1], vertical_alignment="center")
    heading.subheader("📋 资产明细 (Positions Detail)")
    closed_count = int((~is_held).sum())
    show_closed = controls.toggle(
        f"显示已清仓（{closed_count}）",
        key="show_closed_positions",
        disabled=closed_count == 0,
    )
    
    # Select columns for display
    for column in ["price_market_time", "price_fetched_at"]:
        if column not in df:
            df[column] = None
        df[column] = df[column].map(display_time)
    df["price_kind"] = df.get("price_kind", pd.Series(index=df.index, dtype=object)).map({
        "quote": "市场报价", "daily_close": "日线价格", "nav": "基金净值", "manual": "手动录入",
    }).fillna("未记录")
    detail_df = df.loc[is_held].sort_values(
        "converted_current_value", ascending=False, na_position="last", kind="stable"
    )
    if show_closed:
        detail_df = pd.concat([detail_df, df.loc[~is_held]])
    display_df = detail_df.reindex(columns=[
        "account_name", "asset_symbol", "asset_name", "currency",
        "total_quantity", "average_cost", "current_price",
        "current_value", "unrealized_pnl", "realized_pnl",
        "price_status", "price_source", "price_kind", "price_market_time", "price_fetched_at",
        "price_fallback_reason", "price_error"
    ]).rename(columns={
        "account_name": "账户",
        "asset_symbol": "代码",
        "asset_name": "名称",
        "currency": "货币",
        "total_quantity": "持仓数量",
        "average_cost": "持仓成本价",
        "current_price": "当前价",
        "current_value": "当前总价值",
        "unrealized_pnl": "未实现收益",
        "realized_pnl": "已实现收益",
        "price_status": "行情状态",
        "price_source": "数据源",
        "price_kind": "价格类型",
        "price_market_time": "行情时间",
        "price_fetched_at": "采集成功时间",
        "price_fallback_reason": "切换备用源原因",
        "price_error": "行情错误"
    })
    
    if display_df.empty:
        st.info("当前没有持仓，打开「显示已清仓」可查看历史记录。")
    else:
        st.dataframe(display_df, width="stretch", hide_index=True)
