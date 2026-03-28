import yfinance as yf
from cachetools import TTLCache, cached
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

# Cache for 5 minutes (300 seconds), max 1000 items
price_cache = TTLCache(maxsize=1000, ttl=300)

from typing import Optional

@cached(cache=price_cache)
def fetch_single_price(symbol: str) -> Optional[float]:
    try:
        ticker = yf.Ticker(symbol)
        # fast_info is much faster for getting live quotes without downloading history
        # Using .get for safely retrieving "lastPrice" backwards compatibility if needed
        # but fast_info is a property in recent yfinance. 
        if hasattr(ticker, "fast_info") and 'last_price' in ticker.fast_info:
             return float(ticker.fast_info['last_price'])
        # Fallback to fetching today's history
        df = ticker.history(period="1d")
        if not df.empty:
             return float(df['Close'].iloc[-1])
        return None
    except Exception as e:
        logger.error(f"Failed to fetch price for {symbol}: {e}")
        return None

def get_current_prices(symbols: List[str]) -> Dict[str, float]:
    """
    Fetches the current real-time prices for a list of symbols.
    Prices are automatically cached for 5 minutes.
    """
    prices = {}
    unique_symbols = set(symbols)
    for symbol in unique_symbols:
        price = fetch_single_price(symbol)
        if price is not None:
            prices[symbol] = price
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
