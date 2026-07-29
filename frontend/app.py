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

st.title("💹 Personal Finance Dashboard")

if st.button("刷新数据", help="清除页面缓存并重新读取后台行情快照"):
    st.cache_data.clear()

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
    
    # Filter out empty current values for the pie chart
    active_df = df[
        (df["total_quantity"].astype(float) > 0)
        & (df["valuation_available"])
    ]
    
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
    st.subheader("📋 资产明细 (Positions Detail)")
    
    # Select columns for display
    display_df = df[[
        "account_name", "asset_symbol", "asset_name", "currency",
        "total_quantity", "average_cost", "current_price",
        "current_value", "unrealized_pnl", "realized_pnl",
        "price_status", "price_source", "price_as_of", "price_error"
    ]].rename(columns={
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
        "price_as_of": "行情时间",
        "price_error": "行情错误"
    })
    
    # Format some columns
    st.dataframe(display_df, width="stretch", hide_index=True)
