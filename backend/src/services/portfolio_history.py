from typing import List, Dict
from src.database import supabase
from src.services.market_store import (
    get_cached_exchange_rates,
    load_asset_snapshots,
)
from src.schemas.portfolio import PortfolioDailyHistory, PortfolioHistoryResponse
import pandas as pd
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

def calculate_portfolio_history(period: str = "1y", account_id: str = None, base_currency: str = "CNY") -> PortfolioHistoryResponse:
    if supabase is None:
        raise Exception("Supabase client not initialized.")
        
    query = supabase.table("transactions").select("*, assets(*)")
    if account_id:
        query = query.eq("account_id", account_id)
        
    response = query.execute()
    transactions = getattr(response, "data", None) or []
    
    # Sort chronologically
    transactions.sort(key=lambda x: x.get('trade_time', ''))
    
    if not transactions:
        return PortfolioHistoryResponse(history=[], period=period)
        
    # Get all involved asset ids, symbols and currencies.
    market_assets = {}
    custom_assets = set()
    asset_currencies = {}
    warnings = []
    snapshot_times = []
    
    for tx in transactions:
        asset = tx.get("assets")
        if asset:
            sym = asset.get("symbol")
            cur = asset.get("currency", "CNY")
            asset_type = asset.get("asset_type")
            if asset_type == "Custom":
                custom_assets.add(asset.get("id"))
                if sym: asset_currencies[sym] = cur
            else:
                asset_id = asset.get("id")
                if asset_id and sym:
                    market_assets[str(asset_id)] = {
                        "symbol": sym,
                        "name": asset.get("name") or sym,
                    }
                    asset_currencies[sym] = cur

    exchange_rates, fx_snapshots, fx_store_error = get_cached_exchange_rates(
        base_currency,
        list(asset_currencies.values()),
    )
    if fx_store_error:
        warnings.append(fx_store_error)
    for currency in set(asset_currencies.values()):
        if currency.upper() != base_currency.upper() and currency.upper() not in exchange_rates:
            warnings.append(f"缺少 {currency}/{base_currency} 汇率快照。")

    # Fast request path: build the historical price matrix from one persisted
    # snapshot query. Provider downloads only happen in market_collector.py.
    market_snapshots, market_store_error = load_asset_snapshots(market_assets.keys())
    if market_store_error:
        warnings.append(market_store_error)

    market_frames = []
    for asset_id, asset_info in market_assets.items():
        snapshot = market_snapshots.get(asset_id)
        symbol = asset_info["symbol"]
        if not snapshot:
            warnings.append(f"{symbol} 尚无历史行情快照。")
            continue
        history = snapshot.get("history") or {}
        if not history:
            detail = snapshot.get("history_error") or "后台尚未完成历史采集。"
            warnings.append(f"{symbol}: {detail}")
            continue
        series = pd.Series(
            {pd.Timestamp(day): float(close) for day, close in history.items()},
            name=symbol,
            dtype=float,
        ).sort_index()
        market_frames.append(series.to_frame())
        if snapshot.get("history_fetched_at"):
            snapshot_times.append(snapshot["history_fetched_at"])

    prices_df = (
        pd.concat(market_frames, axis=1).sort_index().ffill()
        if market_frames
        else pd.DataFrame()
    )
    
    # Optional logic: custom asset prices
    # For simplicity, we can fetch all custom asset prices and construct a dataframe
    if custom_assets:
        custom_query = supabase.table("custom_asset_prices").select("*").in_("asset_id", list(custom_assets)).order("recorded_at", desc=False)
        custom_response = custom_query.execute()
        custom_records = getattr(custom_response, "data", None) or []
        if custom_records:
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
    
    if transactions and not prices_df.empty:
        first_tx_date = pd.to_datetime(transactions[0].get('trade_time')).tz_localize(None).normalize()
        prices_df = prices_df[prices_df.index >= first_tx_date]
        cutoff = _period_cutoff(period)
        if cutoff is not None:
            prices_df = prices_df[prices_df.index >= cutoff]

    if prices_df.empty:
        return PortfolioHistoryResponse(
            history=[],
            period=period,
            data_status="unavailable",
            warnings=_dedupe(warnings),
            data_as_of=_latest_time(snapshot_times),
        )
        
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
                currency = asset_currencies.get(sym, "CNY").upper()
                rate = exchange_rates.get(currency)
                if rate is None:
                    continue
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
        
    return PortfolioHistoryResponse(
        history=history,
        period=period,
        data_status="partial" if warnings else "ok",
        warnings=_dedupe(warnings),
        data_as_of=_latest_time(snapshot_times),
    )


def _period_cutoff(period: str):
    now = pd.Timestamp.now().tz_localize(None).normalize()
    if period == "ytd":
        return pd.Timestamp(year=now.year, month=1, day=1)
    days = {
        "1mo": 30,
        "3mo": 90,
        "6mo": 180,
        "1y": 365,
        "3y": 365 * 3,
        "10y": 365 * 10,
    }.get(period)
    return now - pd.Timedelta(days=days) if days else None


def _dedupe(messages):
    return list(dict.fromkeys(message for message in messages if message))


def _latest_time(values):
    parsed = []
    for value in values:
        try:
            parsed.append(
                datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            )
        except (TypeError, ValueError):
            continue
    return max(parsed) if parsed else None
