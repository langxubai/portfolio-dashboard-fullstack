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
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Asset Value", f"{total_asset_value:,.2f}")
    col2.metric("Total Unrealized PnL", f"{total_unrealized_pnl:,.2f}", 
                delta=f"{total_unrealized_pnl:,.2f}", delta_color="normal")
    
    if total_asset_value > 0:
        total_pnl_percent = (total_unrealized_pnl / (total_asset_value - total_unrealized_pnl)) * 100
    else:
        total_pnl_percent = 0.0
    col3.metric("PnL %", f"{total_pnl_percent:.2f}%", 
                delta=f"{total_pnl_percent:.2f}%", delta_color="normal")

    st.markdown("---")

    # 2. Charts Section
    st.subheader("📊 Portfolio Overview")
    
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
    
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        # Pie Chart: Allocation by Asset Value
        fig_pie = px.pie(df, values="current_value", names="asset_symbol", 
                         title="Asset Allocation", hole=0.3)
        st.plotly_chart(fig_pie, use_container_width=True)
        
    with chart_col2:
        # Bar Chart: PNL by Asset
        fig_bar = px.bar(df, x="asset_symbol", y="unrealized_pnl", 
                         title="Unrealized PnL by Asset",
                         color="unrealized_pnl", color_continuous_scale="rdylgn")
        st.plotly_chart(fig_bar, use_container_width=True)
        
    st.markdown("---")
    
    # 3. Detailed Data Table
    st.subheader("📋 Positions Detail")
    
    # Select columns for display
    display_df = df[[
        "account_name", "asset_symbol", "asset_name", 
        "total_quantity", "average_cost", "current_price", 
        "current_value", "unrealized_pnl", "unrealized_pnl_percent"
    ]].rename(columns={
        "account_name": "Account",
        "asset_symbol": "Symbol",
        "asset_name": "Asset Name",
        "total_quantity": "Quantity",
        "average_cost": "Avg Cost",
        "current_price": "Current Price",
        "current_value": "Total Value",
        "unrealized_pnl": "Unr PnL",
        "unrealized_pnl_percent": "PnL %"
    })
    
    # Format some columns
    st.dataframe(display_df, use_container_width=True, hide_index=True)

