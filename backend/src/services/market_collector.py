"""Independent, bounded collectors. Successful groups publish immediately."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import logging
import math
import threading

from src.database import supabase
from src.services.market_process import call_provider
from src.services.market_store import (
    SUPPORTED_CURRENCIES, load_all_asset_snapshots, patch_asset_snapshot,
    upsert_fx_snapshots, utc_now_iso,
)

logger = logging.getLogger(__name__)
_quote_lock = threading.Lock()
_history_lock = threading.Lock()


def _load_assets():
    if supabase is None:
        raise RuntimeError("Supabase client 未初始化")
    response = supabase.table("assets").select("id,symbol,asset_type,currency").execute()
    return [a for a in response.data if a["asset_type"] != "Custom" and a.get("symbol")]


def _timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _save_quote(asset, quote, error, existing, fallback_reason=None):
    now = utc_now_iso()
    changes = {"quote_attempted_at": now, "quote_status": "error",
               "quote_error": error or "所有适用数据源均未返回有效报价", "updated_at": now}
    if quote:
        try:
            price = float(quote["current_price"])
            at = _timestamp(quote["as_of"])
            old_at = existing.get(str(asset["id"]), {}).get("quote_as_of")
            if not math.isfinite(price) or price <= 0:
                raise ValueError("无效价格")
            if old_at and at < _timestamp(old_at):
                raise ValueError("数据源行情时间早于已保存行情，保留已有价格")
            previous = quote.get("previous_close")
            if previous is not None and (not math.isfinite(float(previous)) or float(previous) <= 0):
                previous = None
            changes.update({
                "current_price": price, "previous_close": previous,
                "source": quote["source"], "quote_as_of": quote["as_of"],
                "quote_kind": quote["kind"], "quote_fetched_at": now,
                "quote_fallback_reason": fallback_reason,
                "quote_status": "ok", "quote_error": None,
            })
        except (ValueError, TypeError, KeyError) as exc:
            changes["quote_error"] = str(exc)
    store_error = patch_asset_snapshot(asset, changes)
    return {"symbol": asset["symbol"], "ok": not store_error and changes["quote_status"] == "ok",
            "source": changes.get("source"), "error": store_error or changes["quote_error"]}


def _quote_group(assets, primary, existing):
    payload = assets[0] if primary == "coinbase" else assets
    quotes, error = call_provider(primary, payload, timeout=10)
    results = []
    missing = []
    for asset in assets:
        quote = quotes.get(asset["symbol"])
        if quote:
            results.append(_save_quote(asset, quote, None, existing))
        else:
            missing.append(asset)
    if missing:
        fallback, fallback_error = call_provider("yahoo", [a["symbol"] for a in missing], timeout=15)
        for asset in missing:
            reason = error or f"{primary} 未覆盖或未返回该标的"
            results.append(_save_quote(asset, fallback.get(asset["symbol"]),
                                       fallback_error or reason, existing, reason))
    return results


def _fund_quote(asset, existing):
    quotes, error = call_provider("fund", asset["symbol"], timeout=20)
    return [_save_quote(asset, quotes.get(asset["symbol"]), error, existing)]


def _fx_quotes():
    quotes, error = call_provider("frankfurter", list(SUPPORTED_CURRENCIES), timeout=10)
    pairs = [f"{target}/{base}" for target in SUPPORTED_CURRENCIES
             for base in SUPPORTED_CURRENCIES if target != base]
    missing = [pair for pair in pairs if pair not in quotes]
    if missing:
        fallback, fallback_error = call_provider("yahoo", [p.replace("/", "") + "=X" for p in missing], timeout=15)
        for pair in missing:
            quote = fallback.get(pair.replace("/", "") + "=X")
            if quote:
                quotes[pair] = quote
        error = fallback_error or error
    now = utc_now_iso()
    successes, failures = [], []
    for pair in pairs:
        target, base = pair.split("/")
        row = {"pair": pair, "target_currency": target, "base_currency": base,
               "attempted_at": now, "updated_at": now}
        quote = quotes.get(pair)
        if quote and math.isfinite(float(quote["current_price"])) and float(quote["current_price"]) > 0:
            row.update({"rate": quote["current_price"], "source": quote["source"],
                        "as_of": quote["as_of"], "kind": quote["kind"],
                        "status": "ok", "error": None, "fetched_at": now})
            successes.append(row)
        else:
            failures.append(pair)
    store_error = upsert_fx_snapshots(successes)
    # Failure updates preserve the last successful rate and its provenance.
    if failures and supabase is not None:
        try:
            supabase.table("market_fx_snapshots").update({
                "status": "error", "error": error or "汇率源无数据", "attempted_at": now,
            }).in_("pair", failures).execute()
        except Exception:
            store_error = "汇率状态保存失败"
    return [{"symbol": "汇率", "ok": not failures and not store_error,
             "source": "frankfurter", "error": store_error or (error if failures else None)}]


def refresh_market_quotes():
    if not _quote_lock.acquire(blocking=False):
        return [{"symbol": "价格", "ok": False, "error": "已有价格更新正在运行"}]
    try:
        assets = _load_assets()
        existing, error = load_all_asset_snapshots(include_history=False)
        if error:
            return [{"symbol": "数据库", "ok": False, "error": error}]
        results = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            stocks = [a for a in assets if a["asset_type"] not in {"FundCN", "Crypto"}]
            futures = [pool.submit(_fx_quotes)]
            if stocks:
                futures.append(pool.submit(_quote_group, stocks, "tencent", existing))
            for asset in assets:
                if asset["asset_type"] == "FundCN":
                    futures.append(pool.submit(_fund_quote, asset, existing))
                elif asset["asset_type"] == "Crypto":
                    futures.append(pool.submit(_quote_group, [asset], "coinbase", existing))
            for future in as_completed(futures):
                try:
                    results.extend(future.result())
                except Exception as exc:
                    logger.exception("Quote group failed")
                    results.append({"symbol": "采集任务", "ok": False, "error": type(exc).__name__})
        return results
    finally:
        _quote_lock.release()


def _history_group(assets, provider, period):
    histories, error = call_provider(provider, {"symbols": [a["symbol"] for a in assets], "period": period}, timeout=30)
    results = []
    for asset in assets:
        now = utc_now_iso()
        history = histories.get(asset["symbol"])
        changes = {"history_attempted_at": now, "history_status": "error",
                   "history_error": error or "历史行情源未返回数据"}
        if history:
            changes.update({"history": history, "history_status": "ok", "history_error": None,
                            "history_source": provider, "history_fetched_at": now})
        store_error = patch_asset_snapshot(asset, changes)
        results.append({"symbol": asset["symbol"], "ok": bool(history) and not store_error,
                        "error": store_error or changes["history_error"]})
    return results


def refresh_market_history(period="max"):
    if not _history_lock.acquire(blocking=False):
        return [{"symbol": "历史曲线", "ok": False, "error": "历史曲线更新已在运行"}]
    try:
        assets = _load_assets()
        results = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            yahoo = [a for a in assets if a["asset_type"] != "FundCN"]
            futures = [pool.submit(_history_group, yahoo, "yahoo_history", period)] if yahoo else []
            futures.extend(pool.submit(_history_group, [a], "fund_history", period)
                           for a in assets if a["asset_type"] == "FundCN")
            for future in as_completed(futures):
                try:
                    results.extend(future.result())
                except Exception as exc:
                    logger.exception("History group failed")
                    results.append({"symbol": "历史曲线", "ok": False, "error": type(exc).__name__})
        return results
    finally:
        _history_lock.release()
