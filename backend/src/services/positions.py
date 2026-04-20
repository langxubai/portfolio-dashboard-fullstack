from decimal import Decimal, InvalidOperation
from typing import List, Dict, Tuple
from src.database import supabase
from src.schemas.positions import PositionResponse
from src.services.market_data import get_current_prices, fetch_fund_cn_price
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
    normal_symbols = []
    custom_asset_ids = []
    fund_cn_symbols = []
    
    for p in active_positions:
        if "symbol" in p:
            if p.get("asset_type") == "Custom":
                custom_asset_ids.append(p["asset_id"])
            elif p.get("asset_type") == "FundCN":
                fund_cn_symbols.append(p["symbol"])
            else:
                normal_symbols.append(p["symbol"])
                
    normal_symbols = list(set(normal_symbols))
    custom_asset_ids = list(set(custom_asset_ids))
    fund_cn_symbols = list(set(fund_cn_symbols))
    
    current_prices = get_current_prices(normal_symbols) if normal_symbols else {}
    
    # Fetch FundCN prices via AkShare
    fund_cn_prices: Dict[str, Dict[str, float]] = {}
    for sym in fund_cn_symbols:
        price_data = fetch_fund_cn_price(sym)
        if price_data is not None:
            fund_cn_prices[sym] = price_data
    
    # Fetch custom prices from DB
    # Map: asset_id -> latest price (float), fetched once ordered by recorded_at desc
    custom_latest_prices: Dict[str, float] = {}
    if custom_asset_ids:
        query = supabase.table("custom_asset_prices").select("asset_id, price").in_("asset_id", custom_asset_ids).order("recorded_at", desc=True)
        data, count = query.execute()
        if data and data[1]:
            for row in data[1]:
                a_id = row["asset_id"]
                if a_id not in custom_latest_prices:
                    custom_latest_prices[a_id] = float(row["price"])

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

        if pos.get("asset_type") == "Custom":
            # For Custom assets, always resolve by asset_id to avoid symbol collisions.
            # No previous_close concept — price is only updated manually.
            a_id = pos["asset_id"]
            if a_id in custom_latest_prices:
                price = custom_latest_prices[a_id]
            else:
                # No price ever recorded: fall back to average_cost so that
                # current_value == total_cost and unrealized_pnl == 0.
                price = float(pos.get("average_cost", 0) or 0)
        elif pos.get("asset_type") == "FundCN":
            # Chinese OTC fund: price fetched via AkShare, keyed by symbol.
            price_data = fund_cn_prices.get(symbol, {})
            price = price_data.get("current_price")
            prev_close = price_data.get("previous_close")
        else:
            price_data = current_prices.get(symbol, {})
            if isinstance(price_data, float):  # defensive fallback
                price = price_data
            else:
                price = price_data.get("current_price")
                prev_close = price_data.get("previous_close")
        
        pr_data = {
            "account_id": pos["account_id"],
            "asset_id": pos["asset_id"],
            "symbol": symbol,
            "name": pos["name"],
            "asset_type": pos["asset_type"],
            "currency": pos["currency"],
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
