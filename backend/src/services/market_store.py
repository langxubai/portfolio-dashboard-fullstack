"""Persistence helpers for background-refreshed market data.

The HTTP request path must never call Yahoo Finance or AkShare directly.  This
module is the boundary between request handlers/background collectors and the
protected Supabase snapshot tables.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.database import supabase


logger = logging.getLogger(__name__)

ASSET_SNAPSHOT_TABLE = "market_asset_snapshots"
FX_SNAPSHOT_TABLE = "market_fx_snapshots"
SUPPORTED_CURRENCIES = ("CNY", "USD", "HKD", "EUR", "JPY", "GBP", "SGD")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _response_data(response: Any) -> List[Dict[str, Any]]:
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


def _friendly_store_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if (
        "market_asset_snapshots" in lowered
        or "market_fx_snapshots" in lowered
        or "pgrst205" in lowered
        or "could not find the table" in lowered
    ):
        return "行情快照表尚未安装，请执行 backend/scripts/init_db.sql 中的第 6、7 节。"
    if "42501" in lowered or "permission denied" in lowered:
        return "后端无权访问行情快照表，请配置 SUPABASE_SERVICE_KEY。"
    return f"行情快照存储不可用：{message[:240]}"


def load_asset_snapshots(
    asset_ids: Iterable[str],
) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    ids = sorted({str(asset_id) for asset_id in asset_ids if asset_id})
    if not ids:
        return {}, None
    if supabase is None:
        return {}, "Supabase client 未初始化。"

    try:
        response = (
            supabase.table(ASSET_SNAPSHOT_TABLE)
            .select("*")
            .in_("asset_id", ids)
            .execute()
        )
        rows = _response_data(response)
        return {str(row["asset_id"]): row for row in rows}, None
    except Exception as exc:
        error = _friendly_store_error(exc)
        logger.warning("Failed to load asset market snapshots: %s", error)
        return {}, error


def load_all_asset_snapshots(include_history=True) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    if supabase is None:
        return {}, "Supabase client 未初始化。"
    try:
        columns = "*" if include_history else (
            "asset_id,symbol,source,current_price,previous_close,quote_status,quote_error,"
            "quote_attempted_at,quote_fetched_at,quote_as_of,quote_kind,quote_fallback_reason,"
            "history_status,history_error,history_fetched_at,history_source"
        )
        response = supabase.table(ASSET_SNAPSHOT_TABLE).select(columns).execute()
        rows = _response_data(response)
        return {str(row["asset_id"]): row for row in rows}, None
    except Exception as exc:
        error = _friendly_store_error(exc)
        logger.warning("Failed to load all asset market snapshots: %s", error)
        return {}, error


def upsert_asset_snapshots(rows: List[Dict[str, Any]]) -> Optional[str]:
    if not rows:
        return None
    if supabase is None:
        return "Supabase client 未初始化。"

    try:
        (
            supabase.table(ASSET_SNAPSHOT_TABLE)
            .upsert(rows, on_conflict="asset_id")
            .execute()
        )
        return None
    except Exception as exc:
        error = _friendly_store_error(exc)
        logger.error("Failed to upsert asset market snapshots: %s", error)
        return error


def patch_asset_snapshot(asset, changes):
    """Insert once, then update only the fields owned by this collector."""
    if supabase is None:
        return "Supabase client 未初始化。"
    try:
        supabase.table(ASSET_SNAPSHOT_TABLE).upsert({
            "asset_id": str(asset["id"]), "symbol": asset["symbol"],
            "source": "pending",
        }, on_conflict="asset_id", ignore_duplicates=True).execute()
        supabase.table(ASSET_SNAPSHOT_TABLE).update(changes).eq("asset_id", str(asset["id"])).execute()
        return None
    except Exception as exc:
        logger.exception("Snapshot update failed")
        return _friendly_store_error(exc)


def fx_pair_key(target: str, base: str) -> str:
    return f"{target.upper()}/{base.upper()}"


def load_fx_snapshots(
    base: str,
    targets: Iterable[str],
) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    normalized_base = base.upper()
    normalized_targets = sorted({target.upper() for target in targets if target})
    pairs = [
        fx_pair_key(target, normalized_base)
        for target in normalized_targets
        if target != normalized_base
    ]

    rows_by_target: Dict[str, Dict[str, Any]] = {
        normalized_base: {
            "pair": fx_pair_key(normalized_base, normalized_base),
            "target_currency": normalized_base,
            "base_currency": normalized_base,
            "rate": 1.0,
            "status": "ok",
            "source": "identity",
        }
    }
    if not pairs:
        return rows_by_target, None
    if supabase is None:
        return rows_by_target, "Supabase client 未初始化。"

    try:
        response = (
            supabase.table(FX_SNAPSHOT_TABLE)
            .select("*")
            .in_("pair", pairs)
            .execute()
        )
        for row in _response_data(response):
            rows_by_target[str(row["target_currency"]).upper()] = row
        return rows_by_target, None
    except Exception as exc:
        error = _friendly_store_error(exc)
        logger.warning("Failed to load FX market snapshots: %s", error)
        return rows_by_target, error


def load_all_fx_snapshots() -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    if supabase is None:
        return {}, "Supabase client 未初始化。"
    try:
        response = supabase.table(FX_SNAPSHOT_TABLE).select("*").execute()
        rows = _response_data(response)
        return {str(row["pair"]): row for row in rows}, None
    except Exception as exc:
        error = _friendly_store_error(exc)
        logger.warning("Failed to load all FX market snapshots: %s", error)
        return {}, error


def get_cached_exchange_rates(
    base: str,
    targets: Iterable[str],
) -> Tuple[Dict[str, float], Dict[str, Dict[str, Any]], Optional[str]]:
    snapshots, store_error = load_fx_snapshots(base, targets)
    rates: Dict[str, float] = {}
    for target, snapshot in snapshots.items():
        rate = snapshot.get("rate")
        if rate is not None:
            rates[target] = float(rate)
    return rates, snapshots, store_error


def upsert_fx_snapshots(rows: List[Dict[str, Any]]) -> Optional[str]:
    if not rows:
        return None
    if supabase is None:
        return "Supabase client 未初始化。"

    try:
        (
            supabase.table(FX_SNAPSHOT_TABLE)
            .upsert(rows, on_conflict="pair")
            .execute()
        )
        return None
    except Exception as exc:
        error = _friendly_store_error(exc)
        logger.error("Failed to upsert FX market snapshots: %s", error)
        return error
