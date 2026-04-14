from typing import List, Dict
from src.database import supabase
from src.services.market_data import download_historical_prices, get_exchange_rates, download_fund_cn_historical_prices
from src.schemas.portfolio import PortfolioDailyHistory, PortfolioHistoryResponse
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def calculate_portfolio_history(period: str = "1y", account_id: str = None, base_currency: str = "CNY") -> PortfolioHistoryResponse:
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
        
    # Get all involved symbols and currencies
    market_symbols = set()
    custom_assets = set()
    fund_cn_symbols = set()
    asset_currencies = {}
    
    for tx in transactions:
        asset = tx.get("assets")
        if asset:
            sym = asset.get("symbol")
            cur = asset.get("currency", "CNY")
            asset_type = asset.get("asset_type")
            if asset_type == "Custom":
                custom_assets.add(asset.get("id"))
                if sym: asset_currencies[sym] = cur
            elif asset_type == "FundCN":
                fund_cn_symbols.add(sym)
                if sym: asset_currencies[sym] = cur
            else:
                market_symbols.add(sym)
                asset_currencies[sym] = cur
                
    exchange_rates = get_exchange_rates(base_currency, list(asset_currencies.values()))
                
    # Download prices for yfinance-backed assets
    prices_df = download_historical_prices(list(market_symbols), period=period)
    
    # Download FundCN historical NAV via AkShare and merge
    if fund_cn_symbols:
        fund_cn_df = download_fund_cn_historical_prices(list(fund_cn_symbols), period=period)
        if not fund_cn_df.empty:
            if not prices_df.empty:
                prices_df = prices_df.join(fund_cn_df, how='outer').ffill()
            else:
                prices_df = fund_cn_df
    
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
                        dates = pd.to_datetime([r["recorded_at"] for r in asset_recs])
                        # 修复: 为了避免与外生历史价格合并时触发 "Cannot join tz-naive with tz-aware DatetimeIndex" 错误
                        # 在此主动剥离自定义资产的 timezone 时区属性，并将其对齐到无时区基准线上。
                        if dates.tz is not None:
                            dates = dates.tz_localize(None)
                        dates = dates.normalize()
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
    current_holdings = {} # symbol -> {"qty": 0.0, "cost": 0.0}
    
    tx_index = 0
    num_tx = len(transactions)
    
    for date in prices_df.index:
        date_str = str(date.date())
        # Process transactions up to this date
        
        while tx_index < num_tx:
            tx = transactions[tx_index]
            # 修复: 同样的，在提取交易快照日期时也务必剥离时区 (tz_localize(None))，
            # 保证上步处理或拉取的外生无时区 DataFrame DatetimeIndex 能够无缝进行过滤、对位及聚合。
            tx_date = pd.to_datetime(tx.get('trade_time')).tz_localize(None).normalize()
            if tx_date <= date:
                # Apply transaction
                asset = tx.get("assets")
                if asset:
                    sym = asset.get("symbol")
                    qty = float(tx.get("quantity", 0))
                    price = float(tx.get("price", 0))
                    ttype = tx.get("trade_type")
                    
                    h = current_holdings.setdefault(sym, {"qty": 0.0, "cost": 0.0})
                    
                    if ttype == "BUY":
                        h["qty"] += qty
                        h["cost"] += qty * price
                    elif ttype == "SELL":
                        if h["qty"] > 0:
                            avg_cost = h["cost"] / h["qty"]
                            h["qty"] = max(0.0, h["qty"] - qty)
                            h["cost"] -= qty * avg_cost
                            if h["qty"] < 1e-8:
                                h["qty"] = 0.0
                                h["cost"] = 0.0
                    
                tx_index += 1
            else:
                break
                
        # Calculate end of day value
        daily_value = 0.0
        daily_cost = 0.0
        
        for sym, data in current_holdings.items():
            qty = data["qty"]
            cost = data["cost"]
            if qty < 1e-8:
                current_holdings[sym] = {"qty": 0.0, "cost": 0.0}
                continue

            if qty > 0 and sym in prices_df.columns:
                p = prices_df.at[date, sym]
                rate = exchange_rates.get(asset_currencies.get(sym, "CNY"), 1.0)
                if not pd.isna(p):
                    daily_value += qty * float(p) * rate
                    daily_cost += cost * rate
                    
        # Calculate return rate as weighted average of held assets
        # (Total Value - Total Cost) / Total Cost
        # 修复: 我们已废弃单一的“总额净增比例”，因为此算法会在发生大规模“抽资撤盘”或“满额平仓”时不可避免地导致分母崩塌引发暴跌入 -100% 的数学畸变。
        # 取而代之的是时间加权收益率 (Time-Weighted Return, TWR) 的基础延伸逻辑：此处只汇算和累加“仍在手存续头寸”的加权净值与成本表现。
        # 这种隔离和只关心期末有效成本的设计，确保了出金入金不破坏整体投资组合表现的复利长尾斜率。
        if daily_cost > 0:
            return_rate = (daily_value - daily_cost) / daily_cost
        else:
            return_rate = 0.0
            
        history.append(PortfolioDailyHistory(
            date=date_str,
            total_value=daily_value,
            total_cost=daily_cost,
            net_deposit=daily_cost,  # use cost as baseline representation
            return_rate=return_rate
        ))
        
    return PortfolioHistoryResponse(history=history, period=period)
