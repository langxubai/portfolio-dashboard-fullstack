import threading
import yfinance as yf
from cachetools import TTLCache, cached
from typing import Dict, List
import logging

try:
    import akshare as ak
    _AKSHARE_AVAILABLE = True
except ImportError:
    _AKSHARE_AVAILABLE = False
    ak = None

logger = logging.getLogger(__name__)

# Cache for 5 minutes (300 seconds), max 1000 items
# Lock is REQUIRED: TTLCache is NOT thread-safe; concurrent access from the
# scheduler (APScheduler) and HTTP request handlers causes intermittent 500 errors.
price_cache = TTLCache(maxsize=1000, ttl=300)
price_cache_lock = threading.Lock()

from typing import Optional

@cached(cache=price_cache, lock=price_cache_lock)
def fetch_single_price(symbol: str) -> Optional[Dict[str, float]]:
    try:
        ticker = yf.Ticker(symbol)
        price_data = {}
        # fast_info is much faster for getting live quotes without downloading history
        if hasattr(ticker, "fast_info"):
            if 'last_price' in ticker.fast_info:
                price_data['current_price'] = float(ticker.fast_info['last_price'])
            if 'previous_close' in ticker.fast_info:
                price_data['previous_close'] = float(ticker.fast_info['previous_close'])
                
        if 'current_price' in price_data and 'previous_close' in price_data:
             return price_data
             
        # Fallback to fetching today's history
        df = ticker.history(period="5d")
        if not df.empty:
            price_data['current_price'] = float(df['Close'].iloc[-1])
            if len(df) > 1:
                price_data['previous_close'] = float(df['Close'].iloc[-2])
            else:
                price_data['previous_close'] = price_data['current_price']
            return price_data
            
        return None
    except Exception as e:
        logger.error(f"Failed to fetch price for {symbol}: {e}")
        return None

def get_current_prices(symbols: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Fetches the current real-time prices and previous close for a list of symbols.
    Prices are automatically cached for 5 minutes.
    """
    prices = {}
    unique_symbols = set(symbols)
    for symbol in unique_symbols:
        price_data = fetch_single_price(symbol)
        if price_data is not None:
            prices[symbol] = price_data
    return prices

@cached(cache=price_cache, lock=price_cache_lock)
def fetch_exchange_rate(target: str, base: str) -> float:
    """Fetch exchange rate from target currency to base currency (1 target = X base)."""
    if target.upper() == base.upper():
        return 1.0
    
    # yfinance uses symbols like USDCNY=X for USD to CNY
    symbol = f"{target.upper()}{base.upper()}=X"
    try:
        ticker = yf.Ticker(symbol)
        if hasattr(ticker, "fast_info") and 'last_price' in ticker.fast_info:
            return float(ticker.fast_info['last_price'])
        
        # Fallback
        df = ticker.history(period="1d")
        if not df.empty:
            return float(df['Close'].iloc[-1])
    except Exception as e:
        logger.error(f"Failed to fetch exchange rate for {target} to {base}: {e}")
    
    return 1.0  # Safe fallback if fetching fails

def get_exchange_rates(base: str, targets: List[str]) -> Dict[str, float]:
    """
    Fetches exchange rates from a list of target currencies to a base currency.
    """
    rates = {}
    for target in set(targets):
        if not target:
            continue
        rates[target] = fetch_exchange_rate(target, base)
    return rates

import pandas as pd
from datetime import timedelta

@cached(cache=price_cache, lock=price_cache_lock)
def fetch_historical_price_for_window(symbol: str, window_minutes: int) -> Optional[float]:
    """
    Fetches the price from approximately `window_minutes` ago.
    Useful for CHANGE_PERCENT and CHANGE_ABS alert rules.
    """
    try:
        ticker = yf.Ticker(symbol)
        # Get at least (window/1440 + 5) days to ensure we cover weekends/holidays
        days_to_fetch = max(5, int(window_minutes / 1440) + 5)
        # Use 1m for small windows (up to 7 days), else 5m/1h depending on window size
        # yfinance allows 1m max for 7d
        if days_to_fetch <= 7:
            period = f"{days_to_fetch}d"
            interval = "1m"
        else:
            period = "1mo"
            interval = "1h"
            
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return None
        
        last_dt = df.index[-1]
        target_dt = last_dt - timedelta(minutes=window_minutes)
        
        # Find closest date index
        closest_idx = df.index.get_indexer([target_dt], method="nearest")[0]
        closest_price = float(df['Close'].iloc[closest_idx])
        return closest_price
    except Exception as e:
        logger.error(f"Failed to fetch historical price for window {window_minutes} of {symbol}: {e}")
        return None

def fetch_fund_cn_price(symbol: str) -> Optional[Dict[str, float]]:
    """
    Fetches the latest NAV (Net Asset Value) for a Chinese OTC fund using AkShare.
    The cache key is prefixed with 'FUNDCN:' to avoid collision with yfinance symbols.
    Results are cached in the shared price_cache for 5 minutes.
    """
    cache_key = f"FUNDCN:{symbol}"
    with price_cache_lock:
        if cache_key in price_cache:
            return price_cache[cache_key]

    if not _AKSHARE_AVAILABLE:
        logger.warning("AkShare is not installed; cannot fetch FundCN price.")
        return None

    try:
        df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
        if df is None or df.empty:
            return None
        # Expected columns: 净值日期, 单位净值, 日增长率
        df = df.sort_values(by=df.columns[0])  # sort by date ascending
        current_price = float(df.iloc[-1, 1])   # last row, nav column
        result: Dict[str, float] = {"current_price": current_price}
        if len(df) >= 2:
            result["previous_close"] = float(df.iloc[-2, 1])
        with price_cache_lock:
            price_cache[cache_key] = result
        return result
    except Exception as e:
        logger.error(f"AkShare: failed to fetch FundCN price for {symbol}: {e}")
        return None


def download_fund_cn_historical_prices(symbols: List[str], period: str = "1y") -> pd.DataFrame:
    """
    Downloads historical NAV for a list of Chinese OTC fund codes using AkShare.
    Returns a DataFrame where index is Date and columns are fund codes.
    The `period` parameter is mapped to a rough start date for filtering.
    """
    if not symbols or not _AKSHARE_AVAILABLE:
        return pd.DataFrame()

    # Map yfinance-style period strings to approximate number of days
    period_days = {
        "1mo": 30, "3mo": 90, "6mo": 180,
        "ytd": 365, "1y": 365, "max": 36500,
    }
    days = period_days.get(period, 365)
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)

    df_list = []
    for symbol in symbols:
        try:
            df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势")
            if df is None or df.empty:
                continue
            df = df.sort_values(by=df.columns[0])
            dates = pd.to_datetime(df.iloc[:, 0]).dt.normalize()
            navs = df.iloc[:, 1].astype(float).values
            sym_df = pd.DataFrame({symbol: navs}, index=dates)
            sym_df = sym_df[sym_df.index >= cutoff]
            sym_df = sym_df[~sym_df.index.duplicated(keep='last')]
            df_list.append(sym_df)
        except Exception as e:
            logger.error(f"AkShare: failed to download history for FundCN {symbol}: {e}")
            continue

    if not df_list:
        return pd.DataFrame()

    result_df = pd.concat(df_list, axis=1)
    result_df = result_df.sort_index().ffill()
    return result_df


def download_historical_prices(symbols: List[str], period: str = "1y") -> pd.DataFrame:
    """
    Downloads historical close prices for a list of symbols over a given period.
    Returns a DataFrame where index is Date and columns are symbols with their Close prices.
    """
    if not symbols:
        return pd.DataFrame()
    try:
        df_list = []
        # yf.download can download multiple symbols at once
        data = yf.download(symbols, period=period, interval="1d", group_by="ticker", progress=False)
        
        # If there's only one symbol, yfinance doesn't use MultiIndex for columns
        if len(symbols) == 1:
            sym = symbols[0]
            if "Close" in data.columns:
                df = data[["Close"]].rename(columns={"Close": sym})
                df.index = df.index.normalize() # Ensure index is just date without time
                return df
            return pd.DataFrame()
            
        # For multiple symbols, it returns a MultiIndex column DataFrame (Ticker, PriceType)
        for sym in symbols:
            # yfinance recent versions behavior with MultiIndex:
            if sym in data.columns.levels[0] or (isinstance(data.columns, pd.MultiIndex) and sym in [c[0] for c in data.columns]):
                 try:
                     sym_close = data[sym]["Close"]
                     sym_df = sym_close.to_frame(name=sym)
                     df_list.append(sym_df)
                 except KeyError:
                     continue
            elif "Close" in data.columns: # Sometimes yf flattens if 1 symbol fails
                 pass
                 
        if not df_list:
            return pd.DataFrame()
            
        final_df = pd.concat(df_list, axis=1)
        final_df.index = final_df.index.normalize()
        # forward fill missing prices for weekends / holidays
        final_df = final_df.ffill()
        return final_df
    except Exception as e:
        logger.error(f"Failed to download historical prices for {symbols}: {e}")
        return pd.DataFrame()
