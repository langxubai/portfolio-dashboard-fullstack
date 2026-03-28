import streamlit as st
import pandas as pd
from datetime import datetime
from api_client import api

st.set_page_config(page_title="Transactions", page_icon="📝", layout="wide")

st.title("📝 Transactions Log")

# State trigger
if "tx_trigger" not in st.session_state:
    st.session_state.tx_trigger = 0

def refresh_data():
    st.session_state.tx_trigger += 1

# Fetch references
try:
    accounts = api.get_accounts()
    assets = api.get_assets()
except Exception as e:
    st.error(f"Failed to load references: {e}")
    accounts, assets = [], []

st.subheader("Record New Transaction")

if not accounts or not assets:
    st.warning("Please create at least one Account and one Asset before logging transactions.")
else:
    # Build maps for the dropdowns
    account_map = {f"{acc['name']} ({acc['currency']})": acc["id"] for acc in accounts}
    asset_map = {f"{a['symbol']} - {a['name']}": a["id"] for a in assets}

    with st.form("transaction_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            sel_account = st.selectbox("Account", list(account_map.keys()))
            sel_asset = st.selectbox("Asset", list(asset_map.keys()))
        with col2:
            trade_type = st.selectbox("Trade Type", ["BUY", "SELL", "DIVIDEND"])
            price = st.number_input("Unit Price", min_value=0.0, format="%f", step=0.1)
        with col3:
            quantity = st.number_input("Quantity", min_value=0.0, format="%f", step=1.0)
            trade_time = st.date_input("Trade Date", value=datetime.today())
            
        submitted = st.form_submit_button("Log Transaction")
        if submitted:
            if price > 0 and quantity > 0:
                payload = {
                    "account_id": account_map[sel_account],
                    "asset_id": asset_map[sel_asset],
                    "trade_type": trade_type,
                    "price": price,
                    "quantity": quantity,
                    # backend expects a timestamp/datetime, we combine date with min time
                    "trade_time": f"{trade_time.isoformat()}T00:00:00Z"
                }
                try:
                    api.create_transaction(payload)
                    st.success("Transaction logged successfully!")
                    refresh_data()
                except Exception as e:
                    st.error(f"Error saving transaction: {e}")
            else:
                st.warning("Price and Quantity must be strictly > 0")

st.markdown("---")
st.subheader("Transaction History")

try:
    tx_list = api.get_transactions()
    if tx_list:
        df_tx = pd.DataFrame(tx_list)
        # Map from IDs using api client
        try:
            all_accounts = api.get_accounts()
            all_assets = api.get_assets()
            account_lookup = {acc["id"]: acc["name"] for acc in all_accounts}
            asset_lookup = {ast["id"]: ast["symbol"] for ast in all_assets}
        except Exception:
            account_lookup, asset_lookup = {}, {}
            
        df_tx["account_name"] = df_tx["account_id"].apply(lambda x: account_lookup.get(x, x))
        df_tx["asset_symbol"] = df_tx["asset_id"].apply(lambda x: asset_lookup.get(x, x))
        
        display_df = df_tx[["trade_time", "account_name", "asset_symbol", "trade_type", "price", "quantity"]].copy()
        display_df.sort_values(by="trade_time", ascending=False, inplace=True)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No transaction history.")
except Exception as e:
    st.error(f"Error loading transactions: {e}")
