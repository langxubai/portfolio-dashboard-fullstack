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
