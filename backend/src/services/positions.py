from decimal import Decimal, InvalidOperation
from typing import List, Dict, Tuple
from src.database import supabase
from src.schemas.positions import PositionResponse
from src.services.market_data import get_current_prices
import logging

logger = logging.getLogger(__name__)

def calculate_positions(account_id: str = None) -> List[PositionResponse]:
    if supabase is None:
        raise Exception("Supabase client not initialized.")
        
    # Query transactions with the nested asset details
    query = supabase.table("transactions").select("*, assets(*)")
    if account_id:
        query = query.eq("account_id", account_id)
        
    data, count = query.execute()
    transactions = data[1]
    
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
    normal_symbols = []
    custom_asset_ids = []
    
    for p in active_positions:
        if "symbol" in p:
            if p.get("asset_type") == "Custom":
                custom_asset_ids.append(p["asset_id"])
            else:
                normal_symbols.append(p["symbol"])
                
    normal_symbols = list(set(normal_symbols))
    custom_asset_ids = list(set(custom_asset_ids))
    
    current_prices = get_current_prices(normal_symbols) if normal_symbols else {}
    
    # Fetch custom prices from DB
    if custom_asset_ids:
        query = supabase.table("custom_asset_prices").select("asset_id, price").in_("asset_id", custom_asset_ids).order("recorded_at", desc=True)
        data, count = query.execute()
        if data and data[1]:
            seen_assets = set()
            for row in data[1]:
                a_id = row["asset_id"]
                if a_id not in seen_assets:
                    # Find symbol for this asset_id to map into current_prices
                    for p in active_positions:
                        if p["asset_id"] == a_id:
                            current_prices[p["symbol"]] = float(row["price"])
                            break
                    seen_assets.add(a_id)
    
    # Finalize response
    results = []
    for pos in active_positions:
        symbol = pos["symbol"]
        price_data = current_prices.get(symbol, {})
        if isinstance(price_data, float): # fallback just in case
            price = price_data
            prev_close = None
        else:
            price = price_data.get("current_price")
            prev_close = price_data.get("previous_close")
        
        pr_data = {
            "account_id": pos["account_id"],
            "asset_id": pos["asset_id"],
            "symbol": symbol,
            "name": pos["name"],
            "asset_type": pos["asset_type"],
            "total_quantity": round(pos["total_quantity"], 8).normalize(),
            "average_cost": round(pos["average_cost"], 8).normalize(),
            "realized_pnl": round(pos["realized_pnl"], 4)
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
