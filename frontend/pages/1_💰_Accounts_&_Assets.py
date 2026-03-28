import streamlit as st
import pandas as pd
from api_client import api

st.set_page_config(page_title="Accounts & Assets", page_icon="💰", layout="wide")

st.title("💰 Accounts & Assets Management")

# Default values for state logic
if "update_trigger" not in st.session_state:
    st.session_state.update_trigger = 0

def refresh_data():
    st.session_state.update_trigger += 1

col1, col2 = st.columns(2)

with col1:
    st.header("Accounts")
    try:
        accounts = api.get_accounts()
        if accounts:
            df_accounts = pd.DataFrame(accounts)
            st.dataframe(df_accounts[["id", "name", "currency"]], use_container_width=True, hide_index=True)
        else:
            st.info("No accounts found.")
    except Exception as e:
        st.error(f"Error loading accounts: {e}")
        
    st.subheader("Add Account")
    with st.form("add_account_form"):
        acc_name = st.text_input("Name", placeholder="e.g. 华泰证券, Schwab, Binance")
        acc_currency = st.text_input("Currency", placeholder="e.g. CNY, USD")
        submitted = st.form_submit_button("Create Account")
        if submitted:
            if acc_name and acc_currency:
                try:
                    api.create_account({"name": acc_name, "currency": acc_currency})
                    st.success("Account created successfully!")
                    refresh_data()
                except Exception as e:
                    st.error(f"Failed to create: {e}")
            else:
                st.warning("Please fill out all fields.")

with col2:
    st.header("Assets")
    try:
        assets = api.get_assets()
        if assets:
            df_assets = pd.DataFrame(assets)
            st.dataframe(df_assets[["id", "symbol", "name", "asset_type"]], use_container_width=True, hide_index=True)
        else:
            st.info("No assets found.")
    except Exception as e:
        st.error(f"Error loading assets: {e}")
        
    st.subheader("Add Asset")
    with st.form("add_asset_form"):
        asset_symbol = st.text_input("Symbol", placeholder="e.g. AAPL, 00700.HK, BTC-USD")
        asset_name = st.text_input("Name", placeholder="e.g. Apple Inc., Tencent")
        # Can be flexible string, using dropdown for common ones
        asset_type = st.selectbox("Asset Type", ["Stock", "Crypto", "Fund", "ETF"])
        
        submitted = st.form_submit_button("Create Asset")
        if submitted:
            if asset_symbol and asset_name:
                try:
                    api.create_asset({
                        "symbol": asset_symbol.upper(),
                        "name": asset_name,
                        "asset_type": asset_type
                    })
                    st.success("Asset created successfully!")
                    refresh_data()
                except Exception as e:
                    st.error(f"Failed to create: {e}")
            else:
                st.warning("Please fill out all fields.")
