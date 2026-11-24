from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import List, Dict
from src.database import supabase
from src.schemas.positions import PositionResponse
from src.services.market_store import load_asset_snapshots
import logging

logger = logging.getLogger(__name__)

def calculate_positions(account_id: str = None) -> List[PositionResponse]:
    if supabase is None:
        raise Exception("Supabase client not initialized.")
        
    # Query transactions with the nested asset details
    query = supabase.table("transactions").select("*, assets(*)")
    if account_id:
        query = query.eq("account_id", account_id)
        
    response = query.execute()
    transactions = getattr(response, "data", None) or []
    
    # Sort transactions chronologically to calculate cost correctly
    # Assumes trade_time is in ISO format
    transactions.sort(key=lambda x: x.get('trade_time', ''))
    
    positions_dict = {}
    
    for tx in transactions:
        asset = tx.get("assets")
        if not asset:
            continue
            
        acc_id = tx.get("account_id")
        ast_id = tx.get("asset_id")
        key = (acc_id, ast_id)
        
        if key not in positions_dict:
            positions_dict[key] = {
                "account_id": acc_id,
                "asset_id": ast_id,
                "symbol": asset.get("symbol"),
                "name": asset.get("name"),
                "asset_type": asset.get("asset_type"),
                "currency": asset.get("currency", "CNY"),
                "total_quantity": Decimal("0"),
                "total_cost": Decimal("0"),
                "realized_pnl": Decimal("0"),
                "realized_cost": Decimal("0"),
            }
            
        pos = positions_dict[key]
        trade_type = tx.get("trade_type")
        try:
            qty = Decimal(str(tx.get("quantity", 0)))
            price = Decimal(str(tx.get("price", 0)))
        except InvalidOperation:
            continue
            
        if trade_type == "BUY":
            pos["total_quantity"] += qty
            pos["total_cost"] += qty * price
        elif trade_type == "SELL":
            if pos["total_quantity"] > Decimal("0"):
                # Average cost of current holdings
                avg_cost = pos["total_cost"] / pos["total_quantity"]
                # Reduce quantity and total_cost proportionally
                pos["total_quantity"] -= qty
                pos["total_cost"] -= qty * avg_cost
                
                # Calculate realized PnL for this sale: Sale Proceeds - Cost of Sold Goods
                pos["realized_pnl"] += qty * price - qty * avg_cost
                pos["realized_cost"] += qty * avg_cost
                
                # Zero out if it dips to zero or below due to floating point inaccuracies/data errors
                if pos["total_quantity"] <= Decimal("1e-8"):
                    pos["total_quantity"] = Decimal("0")
                    pos["total_cost"] = Decimal("0")
        # DIVIDEND does not affect the unit cost basis in this model
        
    # Filter out empty positions AND positions with 0 realized PnL
    active_positions = []
    for pos in positions_dict.values():
        if pos["total_quantity"] < Decimal("1e-8"):
            pos["total_quantity"] = Decimal("0")
            pos["total_cost"] = Decimal("0")
            
        if pos["total_quantity"] > Decimal("0") or abs(pos["realized_pnl"]) > Decimal("1e-8"):
            avg_cost = pos["total_cost"] / pos["total_quantity"] if pos["total_quantity"] > Decimal("0") else Decimal("0")
            pos["average_cost"] = avg_cost
            active_positions.append(pos)
            
    # Fetch market data
    market_asset_ids = []
    custom_asset_ids = []
    
    for p in active_positions:
        if "symbol" in p:
            if p.get("asset_type") == "Custom":
                custom_asset_ids.append(p["asset_id"])
            else:
                market_asset_ids.append(p["asset_id"])
                
    market_asset_ids = list(set(market_asset_ids))
    custom_asset_ids = list(set(custom_asset_ids))

    # Fast request path: read last-known-good snapshots only. Slow Yahoo/AkShare
    # calls are performed by APScheduler jobs in market_collector.py.
    market_snapshots, market_store_error = load_asset_snapshots(market_asset_ids)
    
    # Fetch custom prices from DB
    # Map: asset_id -> latest manually recorded row.
    custom_latest_prices: Dict[str, Dict] = {}
    if custom_asset_ids:
        query = (
            supabase.table("custom_asset_prices")
            .select("asset_id,price,recorded_at")
            .in_("asset_id", custom_asset_ids)
            .order("recorded_at", desc=True)
        )
        response = query.execute()
        rows = getattr(response, "data", None) or []
        for row in rows:
            a_id = row["asset_id"]
            if a_id not in custom_latest_prices:
                custom_latest_prices[a_id] = row

    # NOTE: Custom asset prices are intentionally NOT written into current_prices.
    # current_prices is keyed by symbol, and multiple Custom assets can share the
    # same symbol (e.g. same fund in two accounts with different asset_ids), which
    # would cause one to overwrite the other. Instead, we resolve each Custom
    # position's price directly by asset_id in the finalize loop below.
    
    # Finalize response
    results = []
    for pos in active_positions:
        symbol = pos["symbol"]
        prev_close = None
        price = None
        price_status = "unavailable"
        price_source = None
        price_as_of = None
        price_market_time = None
        price_kind = None
        price_fallback_reason = None
        price_is_stale = False
        price_error = None

        if pos.get("asset_type") == "Custom":
            # For Custom assets, always resolve by asset_id to avoid symbol collisions.
            # No previous_close concept — price is only updated manually.
            a_id = pos["asset_id"]
            if a_id in custom_latest_prices:
                custom_row = custom_latest_prices[a_id]
                price = float(custom_row["price"])
                price_status = "ok"
                price_source = "manual"
                price_as_of = custom_row.get("recorded_at")
                price_market_time = str(price_as_of) if price_as_of else None
                price_kind = "manual"
            else:
                price_error = "尚未录入自定义资产价格。"
        else:
            snapshot = market_snapshots.get(str(pos["asset_id"]))
            if snapshot:
                price = snapshot.get("current_price")
                prev_close = snapshot.get("previous_close")
                price_source = snapshot.get("source")
                price_as_of = snapshot.get("quote_fetched_at")
                price_market_time = snapshot.get("quote_as_of")
                price_kind = snapshot.get("quote_kind")
                price_fallback_reason = snapshot.get("quote_fallback_reason")
                price_error = snapshot.get("quote_error")
                quote_status = snapshot.get("quote_status", "unavailable")
                if price is not None:
                    price_status = quote_status
                    if price_as_of:
                        try:
                            fetched_at = datetime.fromisoformat(
                                str(price_as_of).replace("Z", "+00:00")
                            )
                            age_seconds = (
                                datetime.now(timezone.utc) - fetched_at
                            ).total_seconds()
                            price_is_stale = age_seconds > 900
                        except (TypeError, ValueError):
                            price_is_stale = True
                    else:
                        price_is_stale = True
                    if price_market_time:
                        try:
                            market_day = datetime.fromisoformat(price_market_time.replace("Z", "+00:00")).date()
                            # Keep weekends/holidays distinct from an old successful fetch.
                            if (datetime.now(timezone.utc).date() - market_day).days > 5:
                                price_is_stale = True
                        except ValueError:
                            price_is_stale = True
                    if quote_status != "ok" or price_is_stale:
                        price_status = "stale"
                else:
                    price_status = (
                        "error" if quote_status == "error" else "unavailable"
                    )
            else:
                price_error = market_store_error or "后台尚未生成该资产的行情快照。"
        
        pr_data = {
            "account_id": pos["account_id"],
            "asset_id": pos["asset_id"],
            "symbol": symbol,
            "name": pos["name"],
            "asset_type": pos["asset_type"],
            "currency": pos["currency"],
            "total_quantity": round(pos["total_quantity"], 8).normalize(),
            "average_cost": round(pos["average_cost"], 8).normalize(),
            "realized_pnl": round(pos["realized_pnl"], 4),
            "price_status": price_status,
            "price_source": price_source,
            "price_as_of": price_as_of,
            "price_market_time": price_market_time,
            "price_fetched_at": price_as_of,
            "price_kind": price_kind,
            "price_fallback_reason": price_fallback_reason,
            "price_is_stale": price_is_stale,
            "price_error": price_error,
        }
        
        if pos["realized_cost"] > Decimal("0"):
            pr_data["realized_pnl_percent"] = round(pos["realized_pnl"] / pos["realized_cost"], 4)
        else:
            pr_data["realized_pnl_percent"] = Decimal("0")
            
        if price is not None:
            price_dec = Decimal(str(price))
            pr_data["current_price"] = max(round(price_dec, 4), Decimal("0"))
            curr_val = pos["total_quantity"] * price_dec
            pr_data["current_value"] = round(curr_val, 4)
            unrealized_pnl = curr_val - pos["total_cost"]
            pr_data["unrealized_pnl"] = round(unrealized_pnl, 4)
            if pos["average_cost"] > Decimal("0"):
                pnl_pct = (price_dec - pos["average_cost"]) / pos["average_cost"]
                pr_data["unrealized_pnl_percent"] = round(pnl_pct, 4)
            else:
                pr_data["unrealized_pnl_percent"] = Decimal("0")
                
            if prev_close is not None:
                prev_close_dec = Decimal(str(prev_close))
                pr_data["previous_close"] = max(round(prev_close_dec, 4), Decimal("0"))
                daily_pnl = (price_dec - prev_close_dec) * pos["total_quantity"]
                pr_data["daily_pnl"] = round(daily_pnl, 4)
                if prev_close_dec > Decimal("0"):
                    pr_data["daily_pnl_percent"] = round((price_dec - prev_close_dec) / prev_close_dec, 4)
                
        results.append(PositionResponse(**pr_data))
        
    return results
