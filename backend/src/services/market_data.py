import threading
import yfinance as yf
from cachetools import TTLCache, cached
from typing import Dict, List, Optional
import logging
import os
import pandas as pd

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

# Cache for historical data (1 hour = 3600 seconds)
history_cache = TTLCache(maxsize=100, ttl=3600)
history_cache_lock = threading.Lock()

YFINANCE_TIMEOUT_SECONDS = float(os.environ.get("YFINANCE_TIMEOUT_SECONDS", "8"))


def _extract_close_series(data: pd.DataFrame, symbol: str) -> pd.Series:
    """Handle both yfinance MultiIndex layouts and the single-symbol layout."""
    if data is None or data.empty:
        return pd.Series(dtype=float)

    try:
        if isinstance(data.columns, pd.MultiIndex):
            level_zero = set(data.columns.get_level_values(0))
            if symbol in level_zero:
                series = data[symbol]["Close"]
            elif "Close" in level_zero:
                series = data["Close"][symbol]
            else:
                return pd.Series(dtype=float)
        elif "Close" in data.columns:
            series = data["Close"]
        else:
            return pd.Series(dtype=float)
        return pd.to_numeric(series, errors="coerce").dropna()
    except (KeyError, TypeError):
        return pd.Series(dtype=float)


def fetch_yfinance_quotes(
    symbols: List[str],
) -> tuple[Dict[str, Dict[str, float]], Optional[str]]:
    """Fetch several Yahoo quotes in one bounded request.

    This function is intended for the background collector. Request handlers
    read persisted snapshots and never invoke it.
    """
    unique_symbols = sorted({symbol for symbol in symbols if symbol})
    if not unique_symbols:
        return {}, None

    try:
        data = yf.download(
            unique_symbols,
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
            timeout=YFINANCE_TIMEOUT_SECONDS,
        )
        prices: Dict[str, Dict[str, float]] = {}
        for symbol in unique_symbols:
            closes = _extract_close_series(data, symbol)
            if closes.empty:
                continue
            current_price = float(closes.iloc[-1])
            previous_close = (
                float(closes.iloc[-2]) if len(closes) >= 2 else current_price
            )
            prices[symbol] = {
                "current_price": current_price,
                "previous_close": previous_close,
            }
        if not prices:
            return {}, "Yahoo Finance 未返回任何可用价格。"
        missing = sorted(set(unique_symbols) - set(prices))
        error = f"Yahoo Finance 缺少代码：{', '.join(missing)}" if missing else None
        return prices, error
    except Exception as exc:
        logger.exception("Yahoo Finance batch quote request failed")
        return {}, f"Yahoo Finance 请求失败：{str(exc)[:240]}"

@cached(cache=price_cache, lock=price_cache_lock)
def fetch_single_price(symbol: str) -> Optional[Dict[str, float]]:
    prices, error = fetch_yfinance_quotes([symbol])
    if error:
        logger.error("Failed to fetch price for %s: %s", symbol, error)
    return prices.get(symbol)

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
    
    symbol = f"{target.upper()}{base.upper()}=X"
    prices, error = fetch_yfinance_quotes([symbol])
    if error:
        logger.error(
            "Failed to fetch exchange rate for %s to %s: %s",
            target,
            base,
            error,
        )
    price_data = prices.get(symbol)
    if price_data:
        return float(price_data["current_price"])
    raise RuntimeError(f"Exchange rate unavailable for {target}/{base}")

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

    cache_key = f"FUNDCN_HIST:{','.join(sorted(symbols))}:{period}"
    with history_cache_lock:
        if cache_key in history_cache:
            return history_cache[cache_key].copy()

    # Map yfinance-style period strings to approximate number of days
    period_days = {
        "1mo": 30, "3mo": 90, "6mo": 180,
        "ytd": 365, "1y": 365, "3y": 365 * 3, "10y": 365 * 10, "max": 36500,
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
            dates = pd.to_datetime(df.iloc[:, 0]).dt.tz_localize(None).dt.normalize()
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
    
    with history_cache_lock:
        history_cache[cache_key] = result_df.copy()
        
    return result_df


def download_historical_prices(symbols: List[str], period: str = "1y") -> pd.DataFrame:
    """
    Downloads historical close prices for a list of symbols over a given period.
    Returns a DataFrame where index is Date and columns are symbols with their Close prices.
    """
    if not symbols:
        return pd.DataFrame()
        
    cache_key = f"YF_HIST:{','.join(sorted(symbols))}:{period}"
    with history_cache_lock:
        if cache_key in history_cache:
            return history_cache[cache_key].copy()
            
    try:
        df_list = []
        # yf.download can download multiple symbols at once
        data = yf.download(
            symbols,
            period=period,
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
            timeout=YFINANCE_TIMEOUT_SECONDS,
        )

        for sym in symbols:
            sym_close = _extract_close_series(data, sym)
            if not sym_close.empty:
                df_list.append(sym_close.to_frame(name=sym))
                 
        if not df_list:
            return pd.DataFrame()
            
        final_df = pd.concat(df_list, axis=1)
        if final_df.index.tz is not None:
            final_df.index = final_df.index.tz_localize(None)
        final_df.index = final_df.index.normalize()
        # forward fill missing prices for weekends / holidays
        final_df = final_df.ffill()
        
        with history_cache_lock:
            history_cache[cache_key] = final_df.copy()
            
        return final_df
    except Exception as e:
        logger.exception("Failed to download historical prices for %s: %s", symbols, e)
        return pd.DataFrame()
