import streamlit as st
import pandas as pd
from api_client import api

st.set_page_config(page_title="Alert Rules", page_icon="🔔", layout="wide")

st.title("🔔 Alert Rules Config")

try:
    assets = api.get_assets()
except Exception as e:
    assets = []
    st.error(f"Could not load assets: {e}")

st.subheader("Existing Rules")

try:
    rules = api.get_alert_rules()
    if rules:
        df_rules = pd.DataFrame(rules)
        # Create symbol mapping
        asset_lookup = {a["id"]: a["symbol"] for a in assets} if assets else {}
        df_rules["symbol"] = df_rules["asset_id"].apply(lambda x: asset_lookup.get(x, str(x)))
        
        display_cols = ["id", "symbol", "rule_type", "direction", "target_value", 
                       "time_window_minutes", "cooldown_minutes", "is_active", "last_triggered_at"]
        df_disp = df_rules[display_cols]
        st.dataframe(df_disp, use_container_width=True, hide_index=True)
    else:
        st.info("No alert rules configured.")
except Exception as e:
    st.error(f"Error loading rules: {e}")

st.markdown("---")
st.subheader("Create New Alert")

with st.form("alert_rule_form"):
    asset_map = {f"{a['symbol']} - {a['name']}": a["id"] for a in assets} if assets else {}
    
    sel_asset = st.selectbox("Monitoring Asset", list(asset_map.keys()))
    rule_type = st.selectbox("Rule Type", ["TARGET_PRICE", "CHANGE_PERCENT", "CHANGE_ABS"])
    
    st.caption("TARGET_PRICE: Triggers when price reaches target.  \nCHANGE_PERCENT: Triggers when % change in time window exceeds target (e.g., 0.05 for 5%).  \nCHANGE_ABS: Triggers when absolute price change exceeds target.")
    
    col1, col2 = st.columns(2)
    with col1:
        direction = st.selectbox("Direction", ["UP", "DOWN"])
        target_val = st.number_input("Target Value / Threshold", min_value=0.0, format="%f", step=0.01)
    with col2:
        time_win = st.number_input("Time Window (minutes)", min_value=0, value=60, help="0 means no window limit (good for TARGET_PRICE)")
        cooldown = st.number_input("Cooldown (minutes)", min_value=1, value=1440, help="Wait this long before alerting again.")
        
    submitted = st.form_submit_button("Create Rule")
    if submitted and sel_asset:
        payload = {
            "asset_id": asset_map[sel_asset],
            "rule_type": rule_type,
            "direction": direction,
            "target_value": target_val,
            "time_window_minutes": int(time_win) if time_win > 0 else None,
            "is_active": True,
            "cooldown_minutes": int(cooldown)
        }
        try:
            api.create_alert_rule(payload)
            st.success("Alert Rule created successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to create alert rule: {e}")
            
# Quick Manage actions
st.subheader("Manage Rule (Delete)")
delete_id = st.text_input("Enter Rule UUID to Delete")
if st.button("Delete"):
    if delete_id:
        try:
            api.delete_alert_rule(delete_id)
            st.success("Rule deleted.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to delete rule: {e}")
