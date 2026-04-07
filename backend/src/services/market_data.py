import yfinance as yf
from cachetools import TTLCache, cached
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

# Cache for 5 minutes (300 seconds), max 1000 items
price_cache = TTLCache(maxsize=1000, ttl=300)

from typing import Optional

@cached(cache=price_cache)
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

import pandas as pd
from datetime import timedelta

@cached(cache=price_cache) # you can use a separate cache or the same if keys are different, but wait, args are different so keys will be different
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
