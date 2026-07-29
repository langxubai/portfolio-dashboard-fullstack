"""Background market-data collector.

Slow and unreliable provider calls live here, outside every FastAPI request
path. Successful values are persisted as last-known-good snapshots; a failed
attempt updates status/error fields without erasing the usable old value.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Iterable, List

import pandas as pd

from src.database import supabase
from src.services.market_data import (
    download_fund_cn_historical_prices,
    download_historical_prices,
    fetch_fund_cn_price,
    fetch_yfinance_quotes,
)
from src.services.market_store import (
    SUPPORTED_CURRENCIES,
    fx_pair_key,
    load_all_asset_snapshots,
    load_all_fx_snapshots,
    upsert_asset_snapshots,
    upsert_fx_snapshots,
    utc_now_iso,
)


logger = logging.getLogger(__name__)


def _response_data(response: Any) -> List[Dict[str, Any]]:
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


def _load_assets() -> List[Dict[str, Any]]:
    if supabase is None:
        raise RuntimeError("Supabase client 未初始化。")
    response = (
        supabase.table("assets")
        .select("id,symbol,name,asset_type,currency")
        .execute()
    )
    return _response_data(response)


def _provider_for(asset: Dict[str, Any]) -> str:
    if asset.get("asset_type") == "FundCN":
        return "akshare"
    return "yfinance"


def _base_asset_row(
    asset: Dict[str, Any],
    existing: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    asset_id = str(asset["id"])
    row = dict(existing.get(asset_id, {}))
    row.update(
        {
            "asset_id": asset_id,
            "symbol": asset["symbol"],
            "source": _provider_for(asset),
            "updated_at": utc_now_iso(),
        }
    )
    row.setdefault("history", {})
    row.setdefault("quote_status", "pending")
    row.setdefault("history_status", "pending")
    return row


def _history_map(series: pd.Series) -> Dict[str, float]:
    result: Dict[str, float] = {}
    clean_series = pd.to_numeric(series, errors="coerce").dropna()
    for index, value in clean_series.items():
        timestamp = pd.Timestamp(index)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        result[timestamp.strftime("%Y-%m-%d")] = float(value)
    return result


def refresh_market_quotes() -> None:
    """Refresh latest asset and FX quotes.

    APScheduler executes this synchronous function in its worker executor, so
    provider stalls cannot block FastAPI's asyncio event loop.
    """
    started_at = datetime.now(timezone.utc)
    logger.info("Market quote refresh started")
    try:
        assets = [
            asset
            for asset in _load_assets()
            if asset.get("asset_type") != "Custom" and asset.get("symbol")
        ]
    except Exception:
        logger.exception("Unable to load assets for market quote refresh")
        return

    existing, store_error = load_all_asset_snapshots()
    if store_error:
        logger.error("Market quote refresh skipped: %s", store_error)
        return
    now = utc_now_iso()
    rows: List[Dict[str, Any]] = []

    yahoo_assets = [
        asset for asset in assets if _provider_for(asset) == "yfinance"
    ]
    yahoo_symbols = [str(asset["symbol"]) for asset in yahoo_assets]
    yahoo_prices, yahoo_error = fetch_yfinance_quotes(yahoo_symbols)

    for asset in yahoo_assets:
        row = _base_asset_row(asset, existing)
        symbol = str(asset["symbol"])
        price_data = yahoo_prices.get(symbol)
        row["quote_attempted_at"] = now
        if price_data:
            row.update(
                {
                    "current_price": price_data["current_price"],
                    "previous_close": price_data["previous_close"],
                    "quote_status": "ok",
                    "quote_error": None,
                    "quote_fetched_at": now,
                }
            )
        else:
            row.update(
                {
                    "quote_status": "error",
                    "quote_error": yahoo_error
                    or f"Yahoo Finance 未返回 {symbol} 的价格。",
                }
            )
        rows.append(row)

    for asset in assets:
        if _provider_for(asset) != "akshare":
            continue
        row = _base_asset_row(asset, existing)
        symbol = str(asset["symbol"])
        row["quote_attempted_at"] = now
        price_data = fetch_fund_cn_price(symbol)
        if price_data:
            row.update(
                {
                    "current_price": price_data["current_price"],
                    "previous_close": price_data.get("previous_close"),
                    "quote_status": "ok",
                    "quote_error": None,
                    "quote_fetched_at": now,
                }
            )
        else:
            row.update(
                {
                    "quote_status": "error",
                    "quote_error": f"AkShare 未返回 {symbol} 的净值，详见后端日志。",
                }
            )
        rows.append(row)

    store_error = upsert_asset_snapshots(rows)
    if store_error:
        logger.error("Asset quote refresh could not be persisted: %s", store_error)

    _refresh_fx_quotes(now)
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    logger.info("Market quote refresh finished in %.2fs", elapsed)


def _refresh_fx_quotes(now: str) -> None:
    existing, store_error = load_all_fx_snapshots()
    if store_error:
        logger.error("FX quote refresh skipped: %s", store_error)
        return
    ticker_to_pair: Dict[str, tuple[str, str]] = {}
    for target in SUPPORTED_CURRENCIES:
        for base in SUPPORTED_CURRENCIES:
            if target == base:
                continue
            ticker_to_pair[f"{target}{base}=X"] = (target, base)

    prices, batch_error = fetch_yfinance_quotes(list(ticker_to_pair))
    rows: List[Dict[str, Any]] = []
    for ticker, (target, base) in ticker_to_pair.items():
        pair = fx_pair_key(target, base)
        row = dict(existing.get(pair, {}))
        row.update(
            {
                "pair": pair,
                "target_currency": target,
                "base_currency": base,
                "source": "yfinance",
                "attempted_at": now,
                "updated_at": now,
            }
        )
        price_data = prices.get(ticker)
        if price_data:
            row.update(
                {
                    "rate": price_data["current_price"],
                    "status": "ok",
                    "error": None,
                    "fetched_at": now,
                }
            )
        else:
            row.update(
                {
                    "status": "error",
                    "error": batch_error
                    or f"Yahoo Finance 未返回汇率代码 {ticker}。",
                }
            )
        rows.append(row)

    store_error = upsert_fx_snapshots(rows)
    if store_error:
        logger.error("FX quote refresh could not be persisted: %s", store_error)


def refresh_market_history(period: str = "max") -> None:
    """Refresh daily price history without blocking any user request."""
    started_at = datetime.now(timezone.utc)
    logger.info("Market history refresh started")
    try:
        assets = [
            asset
            for asset in _load_assets()
            if asset.get("asset_type") != "Custom" and asset.get("symbol")
        ]
    except Exception:
        logger.exception("Unable to load assets for market history refresh")
        return

    existing, store_error = load_all_asset_snapshots()
    if store_error:
        logger.error("Market history refresh skipped: %s", store_error)
        return
    now = utc_now_iso()
    rows_by_id: Dict[str, Dict[str, Any]] = {
        str(asset["id"]): _base_asset_row(asset, existing) for asset in assets
    }

    yahoo_assets = [
        asset for asset in assets if _provider_for(asset) == "yfinance"
    ]
    yahoo_symbols = [str(asset["symbol"]) for asset in yahoo_assets]
    yahoo_df = download_historical_prices(yahoo_symbols, period=period)

    for asset in yahoo_assets:
        asset_id = str(asset["id"])
        symbol = str(asset["symbol"])
        row = rows_by_id[asset_id]
        row["history_attempted_at"] = now
        if symbol in yahoo_df.columns:
            history = _history_map(yahoo_df[symbol])
        else:
            history = {}
        if history:
            row.update(
                {
                    "history": history,
                    "history_status": "ok",
                    "history_error": None,
                    "history_fetched_at": now,
                }
            )
        else:
            row.update(
                {
                    "history_status": "error",
                    "history_error": f"Yahoo Finance 未返回 {symbol} 的历史行情。",
                }
            )

    for asset in assets:
        if _provider_for(asset) != "akshare":
            continue
        asset_id = str(asset["id"])
        symbol = str(asset["symbol"])
        row = rows_by_id[asset_id]
        row["history_attempted_at"] = now
        fund_df = download_fund_cn_historical_prices([symbol], period=period)
        history = (
            _history_map(fund_df[symbol])
            if symbol in fund_df.columns
            else {}
        )
        if history:
            row.update(
                {
                    "history": history,
                    "history_status": "ok",
                    "history_error": None,
                    "history_fetched_at": now,
                }
            )
        else:
            row.update(
                {
                    "history_status": "error",
                    "history_error": f"AkShare 未返回 {symbol} 的历史净值。",
                }
            )

    store_error = upsert_asset_snapshots(list(rows_by_id.values()))
    if store_error:
        logger.error("History refresh could not be persisted: %s", store_error)
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    logger.info("Market history refresh finished in %.2fs", elapsed)
