from typing import List, Dict
from src.database import supabase
from src.services.market_data import download_historical_prices
from src.schemas.portfolio import PortfolioDailyHistory, PortfolioHistoryResponse
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def calculate_portfolio_history(period: str = "1y", account_id: str = None) -> PortfolioHistoryResponse:
    if supabase is None:
        raise Exception("Supabase client not initialized.")
        
    query = supabase.table("transactions").select("*, assets(*)")
    if account_id:
        query = query.eq("account_id", account_id)
        
    data, count = query.execute()
    transactions = data[1] if data else []
    
    # Sort chronologically
    transactions.sort(key=lambda x: x.get('trade_time', ''))
    
    if not transactions:
        return PortfolioHistoryResponse(history=[], period=period)
        
    # Get all involved symbols
    market_symbols = set()
    custom_assets = set()
    for tx in transactions:
        asset = tx.get("assets")
        if asset:
            if asset.get("asset_type") == "Custom":
                custom_assets.add(asset.get("id"))
            else:
                market_symbols.add(asset.get("symbol"))
                
    # Download prices
    prices_df = download_historical_prices(list(market_symbols), period=period)
    
    # Optional logic: custom asset prices
    # For simplicity, we can fetch all custom asset prices and construct a dataframe
    if custom_assets:
        custom_query = supabase.table("custom_asset_prices").select("*").in_("asset_id", list(custom_assets)).order("recorded_at", desc=False)
        cdata, ccount = custom_query.execute()
        if cdata and cdata[1]:
            custom_records = cdata[1]
            cdfs = []
            for a_id in custom_assets:
                # get symbol for this a_id
                sym = None
                for tx in transactions:
                    if tx.get("assets", {}).get("id") == a_id:
                        sym = tx.get("assets").get("symbol")
                        break
                if sym:
                    asset_recs = [r for r in custom_records if r["asset_id"] == a_id]
                    if asset_recs:
                        dates = [pd.to_datetime(r["recorded_at"]).normalize() for r in asset_recs]
                        vals = [float(r["price"]) for r in asset_recs]
                        cdf = pd.DataFrame({sym: vals}, index=dates)
                        # resample to daily and forward fill
                        # Ensure we don't fail if duplicate indexes exist
                        cdf = cdf[~cdf.index.duplicated(keep='last')]
                        cdf = cdf.asfreq('D').ffill()
                        cdfs.append(cdf)
            
            if cdfs:
                custom_df = pd.concat(cdfs, axis=1)
                # Merge with market prices_df
                if not prices_df.empty:
                    prices_df = prices_df.join(custom_df, how='outer').ffill()
                else:
                    prices_df = custom_df.ffill()
                    
    # Generate daily portfolio values based on the timeframe in prices_df
    history = []
    if prices_df.empty:
        return PortfolioHistoryResponse(history=[], period=period)
        
    # Track holdings iterativly
    current_holdings = {} # symbol -> quantity
    current_invested = 0.0 # simple net deposit (Buys - Sells)
    
    tx_index = 0
    num_tx = len(transactions)
    
    for date in prices_df.index:
        date_str = str(date.date())
        # Process transactions up to this date
        while tx_index < num_tx:
            tx = transactions[tx_index]
            tx_date = pd.to_datetime(tx.get('trade_time')).tz_localize(None).normalize()
            if tx_date <= date:
                # Apply transaction
                asset = tx.get("assets")
                if asset:
                    sym = asset.get("symbol")
                    qty = float(tx.get("quantity", 0))
                    price = float(tx.get("price", 0))
                    ttype = tx.get("trade_type")
                    if ttype == "BUY":
                        current_holdings[sym] = current_holdings.get(sym, 0.0) + qty
                        current_invested += qty * price
                    elif ttype == "SELL":
                        current_holdings[sym] = max(0.0, current_holdings.get(sym, 0.0) - qty)
                        current_invested -= qty * price # naive net deposit calculation
                tx_index += 1
            else:
                break
                
        # Calculate end of day value
        daily_value = 0.0
        for sym, qty in current_holdings.items():
            if qty > 0 and sym in prices_df.columns:
                p = prices_df.at[date, sym]
                if not pd.isna(p):
                    daily_value += qty * float(p)
                    
        return_rate = (daily_value - current_invested) / current_invested if current_invested > 0 else 0.0
        
        history.append(PortfolioDailyHistory(
            date=date_str,
            total_value=daily_value,
            total_cost=current_invested,
            net_deposit=current_invested,
            return_rate=return_rate
        ))
        
    return PortfolioHistoryResponse(history=history, period=period)
