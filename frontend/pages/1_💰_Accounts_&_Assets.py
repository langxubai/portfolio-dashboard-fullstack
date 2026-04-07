import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo
from api_client import api

COMMON_TIMEZONES = [
    "Asia/Shanghai",
    "Asia/Hong_Kong",
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "UTC"
]

st.set_page_config(page_title="Accounts & Assets", page_icon="💰", layout="wide")

st.title("💰 Accounts & Assets Management")

# Default values for state logic
if "update_trigger" not in st.session_state:
    st.session_state.update_trigger = 0

def refresh_data():
    st.session_state.update_trigger += 1

@st.dialog("Confirm Account Deletion")
def confirm_delete_account(account_id):
    st.warning(f"Are you sure you want to delete account {account_id}?")
    try:
        positions = api.get_positions()
        acc_positions = [p for p in positions if p.get("account_id") == account_id and p.get("total_quantity", 0) > 0]
        asset_count = len(acc_positions)
        st.write(f"This account currently has **{asset_count}** active assets.")
    except Exception as e:
        st.error(f"Could not load position stats: {e}")
        
    if st.button("Confirm Delete", type="primary", key="confirm_del_acc"):
        try:
            api.delete_account(account_id)
            st.success("Account deleted successfully!")
            refresh_data()
            st.rerun()
        except Exception as e:
            st.error(f"Failed to delete account: {e}")

@st.dialog("Confirm Asset Deletion")
def confirm_delete_asset(asset_id):
    st.warning(f"Are you sure you want to delete asset {asset_id}?")
    try:
        positions = api.get_positions()
        asset_positions = [p for p in positions if p.get("asset_id") == asset_id]
        total_quantity = sum(p.get("total_quantity", 0) for p in asset_positions)
        
        rules = api.get_alert_rules()
        asset_rules = [r for r in rules if r.get("asset_id") == asset_id]
        rule_count = len(asset_rules)
        
        st.write(f"This asset currently has a total holding of **{total_quantity}** and **{rule_count}** alert rule(s).")
    except Exception as e:
        st.error(f"Could not load stats: {e}")
        
    if st.button("Confirm Delete", type="primary", key="confirm_del_ast"):
        try:
            api.delete_asset(asset_id)
            st.success("Asset deleted successfully!")
            refresh_data()
            st.rerun()
        except Exception as e:
            st.error(f"Failed to delete asset: {e}")

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

    st.subheader("Delete Account")
    with st.form("delete_account_form"):
        del_acc_id = st.text_input("Account UUID to delete")
        del_submitted = st.form_submit_button("Delete Account")
        if del_submitted:
            if del_acc_id:
                confirm_delete_account(del_acc_id)
            else:
                st.warning("Please enter a UUID.")

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
        asset_type = st.selectbox("Asset Type", ["Stock", "Crypto", "Fund", "ETF", "Custom"])
        
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

    st.subheader("Delete Asset")
    with st.form("delete_asset_form"):
        del_asset_id = st.text_input("Asset UUID to delete")
        del_submitted = st.form_submit_button("Delete Asset")
        if del_submitted:
            if del_asset_id:
                confirm_delete_asset(del_asset_id)
            else:
                st.warning("Please enter a UUID.")

    st.subheader("Update Custom Asset Price")
    custom_assets = [a for a in assets if a.get("asset_type") == "Custom"] if "assets" in locals() and assets else []
    
    if custom_assets:
        with st.form("custom_price_form"):
            asset_options = {a["id"]: f"{a['name']} ({a['symbol']})" for a in custom_assets}
            selected_asset_id = st.selectbox("Select Custom Asset", options=list(asset_options.keys()), format_func=lambda x: asset_options[x])
            
            new_price = st.number_input("New Price", min_value=0.0, format="%.4f")
            
            record_date = st.date_input("Record Date", value=datetime.today().date())
            record_time = st.time_input("Record Time", value=datetime.now().time())
            record_tz = st.selectbox("Timezone", COMMON_TIMEZONES, index=0)
            
            price_submitted = st.form_submit_button("Update Price")
            if price_submitted:
                try:
                    dt = datetime.combine(record_date, record_time)
                    tz = zoneinfo.ZoneInfo(record_tz)
                    dt_aware = dt.replace(tzinfo=tz)
                    api.create_custom_asset_price(selected_asset_id, {"price": float(new_price), "recorded_at": dt_aware.isoformat()})
                    st.success("Price updated successfully!")
                    refresh_data()
                except Exception as e:
                    st.error(f"Failed to update price: {e}")
    else:
        st.info("No 'Custom' assets found to update.")
