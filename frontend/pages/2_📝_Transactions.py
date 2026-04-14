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

st.set_page_config(page_title="Transactions", page_icon="📝", layout="wide")

st.title("📝 Transactions Log")

# State trigger
if "tx_trigger" not in st.session_state:
    st.session_state.tx_trigger = 0

def refresh_data():
    st.session_state.tx_trigger += 1

@st.dialog("Confirm Transaction Deletion")
def confirm_delete_transaction(tx_id):
    st.warning(f"Are you sure you want to delete this transaction?")
    try:
        tx_list = api.get_transactions()
        tx_info = next((tx for tx in tx_list if tx.get("id") == tx_id), None)
        if tx_info:
            tx_qty = tx_info.get("quantity", 0)
            tx_price = tx_info.get("price", 0)
            tx_total = float(tx_qty) * float(tx_price)
            st.write("This transaction details:")
            st.write(f"- **Quantity**: {tx_qty}")
            st.write(f"- **Unit Price**: {tx_price}")
            st.write(f"- **Total Amount**: {tx_total:.4f}")
        else:
            st.write("Could not find transaction details.")
    except Exception as e:
        st.error(f"Could not load stats: {e}")
        
    if st.button("Confirm Delete", type="primary", key="confirm_del_tx"):
        try:
            api.delete_transaction(tx_id)
            st.success("Transaction deleted successfully!")
            refresh_data()
            st.rerun()
        except Exception as e:
            st.error(f"Failed to delete transaction: {e}")

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
    # Sort accounts by name, pinning the most recently added to the top
    accounts = sorted(accounts, key=lambda x: x.get("name", "").lower())
    latest_acc = max(accounts, key=lambda x: x.get("created_at", ""))
    accounts.remove(latest_acc)
    accounts.insert(0, latest_acc)

    # Sort assets by symbol (asset code), pinning the most recently added to the top
    assets = sorted(assets, key=lambda x: x.get("symbol", "").lower())
    latest_asset = max(assets, key=lambda x: x.get("created_at", ""))
    assets.remove(latest_asset)
    assets.insert(0, latest_asset)

    # Build maps for the dropdowns
    account_map = {f"{acc['name']} ({acc['currency']})": acc["id"] for acc in accounts}
    asset_map = {f"{a['symbol']} - {a['name']}": a["id"] for a in assets}

    with st.form("transaction_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            sel_account = st.selectbox("Account", list(account_map.keys()))
            sel_asset = st.selectbox("Asset", list(asset_map.keys()))
            trade_tz = st.selectbox("Timezone", COMMON_TIMEZONES, index=0)
        with col2:
            trade_type = st.selectbox("Trade Type", ["BUY", "SELL", "DIVIDEND"])
            trade_date = st.date_input("Trade Date", value=datetime.today())
            trade_time_str = st.text_input("Trade Time (e.g. 15:14, 151414)", value=datetime.now().strftime("%H:%M:%S"))
        with col3:
            st.info("💡 Fill exactly 2 of 3")
            price = st.number_input("Unit Price", min_value=0.0, format="%f", step=0.1, value=0.0)
            quantity = st.number_input("Quantity", min_value=0.0, format="%f", step=1.0, value=0.0)
            total_amount = st.number_input("Total Amount", min_value=0.0, format="%f", step=1.0, value=0.0)
            
        submitted = st.form_submit_button("Log Transaction")
        if submitted:
            calc_price = float(price)
            calc_qty = float(quantity)
            calc_total = float(total_amount)
            
            non_zeros = sum([1 for v in [calc_price, calc_qty, calc_total] if v > 0])
            valid = False
            
            if non_zeros == 3:
                st.warning("You filled all three fields. We will strictly use Unit Price and Quantity.")
                valid = True
            elif non_zeros == 2:
                if calc_price > 0 and calc_qty > 0:
                    pass # Nothing to calculate
                elif calc_total > 0 and calc_qty > 0:
                    calc_price = round(calc_total / calc_qty, 8)
                elif calc_total > 0 and calc_price > 0:
                    calc_qty = round(calc_total / calc_price, 8)
                valid = True
            else:
                st.warning("Please fill strictly TWO fields among: Unit Price, Quantity, and Total Amount (leave the 3rd as 0.0).")

            if valid:
                if calc_price > 0 and calc_qty > 0:
                    # Parse time string
                    parsed_time = None
                    for fmt in ("%H:%M:%S", "%H:%M", "%H%M%S", "%H%M"):
                        try:
                            parsed_time = datetime.strptime(trade_time_str.strip(), fmt).time()
                            break
                        except ValueError:
                            pass
                    
                    if parsed_time is None:
                        st.error("Invalid Trade Time format. Supported formats: HH:MM:SS, HH:MM, HHMMSS, HHMM.")
                        st.stop()
                        
                    # Combine date and time, and add timezone
                    trade_datetime = datetime.combine(trade_date, parsed_time)
                    tz = zoneinfo.ZoneInfo(trade_tz)
                    trade_datetime_aware = trade_datetime.replace(tzinfo=tz)
                    
                    payload = {
                        "account_id": account_map[sel_account],
                        "asset_id": asset_map[sel_asset],
                        "trade_type": trade_type,
                        "price": calc_price,
                        "quantity": calc_qty,
                        "trade_time": trade_datetime_aware.isoformat()
                    }
                    try:
                        api.create_transaction(payload)
                        st.success(f"Transaction logged successfully! (Price: {calc_price:.4f}, Qty: {calc_qty:.4f})")
                        refresh_data()
                        st.rerun() # Refresh properly so the recent transaction shows up
                    except Exception as e:
                        st.error(f"Error saving transaction: {e}")
                else:
                    st.warning("Calculated Price and Quantity must be strictly > 0")

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
        
        display_df = df_tx[["id", "trade_time", "account_name", "asset_symbol", "trade_type", "price", "quantity"]].copy()
        display_df.sort_values(by="trade_time", ascending=False, inplace=True)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No transaction history.")
except Exception as e:
    st.error(f"Error loading transactions: {e}")

st.markdown("---")
st.subheader("Delete Transaction")
with st.form("delete_tx_form"):
    del_tx_id = st.text_input("Transaction UUID to delete")
    del_submitted = st.form_submit_button("Delete Transaction")
    if del_submitted:
        if del_tx_id:
            confirm_delete_transaction(del_tx_id)
        else:
            st.warning("Please enter a UUID.")
