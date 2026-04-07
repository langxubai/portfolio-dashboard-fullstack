import streamlit as st
import pandas as pd
import plotly.express as px
from api_client import api

st.set_page_config(
    page_title="Personal Finance Dashboard",
    page_icon="💹",
    layout="wide",
)

st.title("💹 Personal Finance Dashboard")

with st.spinner("Loading portfolio data..."):
    try:
        positions_data = api.get_positions()
    except Exception as e:
        st.error(f"Failed to connect to backend: {e}")
        st.info("Make sure FastAPI backend is running on the configured BACKEND_URL.")
        st.stop()

if not positions_data:
    st.info("No active positions found. Go to 'Transactions' to record a new trade.")
else:
    # 1. Summarize metrics
    total_asset_value = sum(float(pos.get("current_value") or 0.0) for pos in positions_data)
    total_unrealized_pnl = sum(float(pos.get("unrealized_pnl") or 0.0) for pos in positions_data)
    total_realized_pnl = sum(float(pos.get("realized_pnl") or 0.0) for pos in positions_data)
    total_daily_pnl = sum(float(pos.get("daily_pnl") or 0.0) for pos in positions_data)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("总资产价值 (Total Value)", f"{total_asset_value:,.2f}",
                delta=f"{total_daily_pnl:,.2f} 今日收益", delta_color="normal")
    col2.metric("未实现收益 (Unrealized PnL)", f"{total_unrealized_pnl:,.2f}")
    
    if total_asset_value > 0:
        total_pnl_percent = (total_unrealized_pnl / (total_asset_value - total_unrealized_pnl)) * 100
    else:
        total_pnl_percent = 0.0
    col3.metric("未实现收益率 (Unrealized %)", f"{total_pnl_percent:.2f}%")
    
    col4.metric("已实现总收益 (Realized PnL)", f"{total_realized_pnl:,.2f}")

    st.markdown("---")

    # 2. Charts Section
    st.subheader("📊 资产总览 (Portfolio Overview)")
    
    # 2.1 History Chart
    st.markdown("##### 📈 收益率曲线图 (Return Rate Curve)")
    period = st.selectbox("选择周期 (Select Period)", ["1mo", "3mo", "6mo", "1y", "ytd", "max"], index=3, format_func=lambda x: {"1mo": "1个月", "3mo": "3个月", "6mo": "6个月", "1y": "1年", "ytd": "今年以来", "max": "全部"}[x])
    with st.spinner("Loading history..."):
        try:
            history_data = api.get_portfolio_history(period=period)
            hist_list = history_data.get("history", [])
            if hist_list:
                hist_df = pd.DataFrame(hist_list)
                # create a sub-selectbox or radio for Total Value vs Return Rate
                chart_type = st.radio("图表类型 (Chart Type)", ["累计净值 (Total Value)", "累计收益率 (Return Rate %)"], horizontal=True)
                if "Return Rate" in chart_type:
                    hist_df["return_rate_pct"] = hist_df["return_rate"] * 100
                    fig_hist = px.line(hist_df, x="date", y="return_rate_pct", title="Portfolio Return Rate %")
                else:
                    fig_hist = px.line(hist_df, x="date", y="total_value", title="Portfolio Total Value")
                st.plotly_chart(fig_hist, use_container_width=True)
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
        acc_list = api.get_accounts()
        acc_map = {a["id"]: a["name"] for a in acc_list}
    except Exception:
        acc_map = {}
    
    df["account_name"] = df["account_id"].apply(lambda x: acc_map.get(x, x))
    
    # Cast decimals strings to float for plotly
    df["current_value"] = df["current_value"].astype(float)
    df["unrealized_pnl"] = df["unrealized_pnl"].astype(float)
    df["realized_pnl"] = df["realized_pnl"].astype(float)
    df["daily_pnl"] = df["daily_pnl"].astype(float).fillna(0.0)
    
    # Filter out empty current values for the pie chart
    active_df = df[df["total_quantity"].astype(float) > 0]
    
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        # Pie Chart: Allocation by Asset Value
        if not active_df.empty:
            fig_pie = px.pie(active_df, values="current_value", names="asset_symbol", 
                             title="资产分配 (Asset Allocation)", hole=0.3)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No active holdings for allocation chart.")
            
    with chart_col2:
        # Bar Chart: PNL by Asset
        if not df.empty:
            fig_bar = px.bar(df, x="asset_symbol", y="unrealized_pnl", 
                             title="各资产未实现收益 (Unrealized PnL by Asset)",
                             color="unrealized_pnl", color_continuous_scale="rdylgn")
            st.plotly_chart(fig_bar, use_container_width=True)
        
    st.markdown("---")
    
    # 3. Detailed Data Table
    st.subheader("📋 资产明细 (Positions Detail)")
    
    # Select columns for display
    display_df = df[[
        "account_name", "asset_symbol", "asset_name", 
        "total_quantity", "average_cost", "current_price", "previous_close",
        "current_value", "daily_pnl", "unrealized_pnl", "realized_pnl"
    ]].rename(columns={
        "account_name": "账户",
        "asset_symbol": "代码",
        "asset_name": "名称",
        "total_quantity": "持仓数量",
        "average_cost": "持仓成本价",
        "current_price": "当前价",
        "previous_close": "前收盘价",
        "current_value": "当前总价值",
        "daily_pnl": "昨日收益",
        "unrealized_pnl": "未实现收益",
        "realized_pnl": "已实现收益"
    })
    
    # Format some columns
    st.dataframe(display_df, use_container_width=True, hide_index=True)

