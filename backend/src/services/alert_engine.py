import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from src.database import supabase
from src.services.market_data import fetch_single_price, fetch_historical_price_for_window
from src.services.notifications import send_alert

logger = logging.getLogger(__name__)

async def evaluate_all_rules():
    """
    Evaluates all active alert rules and dispatches notifications if conditions are met.
    """
    logger.info("Starting alert engine evaluation...")
    
    try:
        # Utilizing Supabase's implicit join syntax via foreign keys to get asset symbol
        rules_response = supabase.table("alert_rules").select("*, assets(symbol, name)").eq("is_active", True).execute()
        rules = rules_response.data
    except Exception as e:
        logger.error(f"Failed to fetch alert rules: {e}")
        return

    if not rules:
        logger.info("No active alert rules found.")
        return

    now = datetime.now(timezone.utc)
    
    for rule in rules:
        try:
            # Check cooldown duration
            if rule.get("last_triggered_at"):
                # Handle ISO format representation properly (ensure UTC compatibility if it has Z)
                trigger_time_str = rule["last_triggered_at"].replace('Z', '+00:00')
                last_triggered = datetime.fromisoformat(trigger_time_str)
                cooldown_minutes = rule.get("cooldown_minutes", 1440)
                if now - last_triggered < timedelta(minutes=cooldown_minutes):
                    # Still in cooldown phase
                    continue

            asset_info = rule.get("assets", {})
            symbol = asset_info.get("symbol")
            
            if not symbol:
                continue

            price_data = fetch_single_price(symbol)
            if price_data is None:
                continue
            # fetch_single_price returns a Dict; extract the numeric price
            current_price = price_data.get("current_price") if isinstance(price_data, dict) else price_data
            if current_price is None:
                continue
            current_price = float(current_price)

            rule_type = rule.get("rule_type")
            direction = rule.get("direction")
            target_value = float(rule.get("target_value"))
            
            triggered = False
            message = ""

            # Check logic based on rule type
            if rule_type == "TARGET_PRICE":
                if direction == "UP" and current_price >= target_value:
                    triggered = True
                    message = f"[{symbol}] reached target price: {current_price} (Target: >={target_value})"
                elif direction == "DOWN" and current_price <= target_value:
                    triggered = True
                    message = f"[{symbol}] reached target price: {current_price} (Target: <={target_value})"
            
            elif rule_type in ["CHANGE_PERCENT", "CHANGE_ABS"]:
                time_window = rule.get("time_window_minutes", 60)
                historical_price = fetch_historical_price_for_window(symbol, time_window)
                if historical_price:
                    change_abs = current_price - historical_price
                    change_pct = (change_abs / historical_price) * 100 if historical_price else 0

                    if rule_type == "CHANGE_ABS":
                        if direction == "UP" and change_abs >= target_value:
                            triggered = True
                            message = f"[{symbol}] Surged by {change_abs:.2f} in {time_window}m! Now {current_price}."
                        elif direction == "DOWN" and change_abs <= -target_value:
                            triggered = True
                            message = f"[{symbol}] Dropped by {-change_abs:.2f} in {time_window}m! Now {current_price}."
                            
                    elif rule_type == "CHANGE_PERCENT":
                        if direction == "UP" and change_pct >= target_value:
                            triggered = True
                            message = f"[{symbol}] Surged by {change_pct:.2f}% in {time_window}m! Now {current_price}."
                        elif direction == "DOWN" and change_pct <= -target_value:
                            triggered = True
                            message = f"[{symbol}] Dropped by {-change_pct:.2f}% in {time_window}m! Now {current_price}."

            if triggered:
                logger.info(f"Rule {rule['id']} triggered: {message}")
                
                # Dispatch Push Notification
                await send_alert(symbol, rule_type, message)
                
                # Update backend record
                update_data = {
                    "last_triggered_at": now.isoformat()
                }
                
                # Typically, TARGET_PRICE is a one-off notification. We deactivate it after trigger.
                if rule_type == "TARGET_PRICE":
                    update_data["is_active"] = False

                supabase.table("alert_rules").update(update_data).eq("id", rule["id"]).execute()

        except Exception as e:
            logger.error(f"Error evaluating rule {rule.get('id')}: {e}")
