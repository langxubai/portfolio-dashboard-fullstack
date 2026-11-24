from fastapi import APIRouter, Query
from typing import Any, List, Dict
from src.services.market_refresh import request_market_refresh, get_refresh_status
from src.services.market_store import (
    get_cached_exchange_rates,
    load_all_asset_snapshots,
    load_all_fx_snapshots,
)

router = APIRouter(
    prefix="/api/market",
    tags=["Market Data"]
)


@router.post("/refresh", status_code=202)
def refresh_prices():
    return request_market_refresh()


@router.get("/refresh")
def refresh_status():
    return get_refresh_status()

@router.get("/exchange-rates", response_model=Dict[str, float])
def get_rates(
    base: str = Query(..., description="Base currency (e.g. CNY)"),
    targets: List[str] = Query(..., description="List of target currencies to get rates for")
):
    """
    Get exchange rates to a base currency.
    Returns a dictionary of target: rate, where 1 target = rate * base.
    """
    rates, snapshots, store_error = get_cached_exchange_rates(
        base=base,
        targets=targets,
    )
    return rates


@router.get("/status", response_model=Dict[str, Any])
def get_market_status():
    """Return provider status without triggering a provider request."""
    snapshots, store_error = load_all_asset_snapshots(include_history=False)
    fx_snapshots, fx_store_error = load_all_fx_snapshots()
    assets = [
        {
            "asset_id": row.get("asset_id"),
            "symbol": row.get("symbol"),
            "source": row.get("source"),
            "quote_status": row.get("quote_status"),
            "quote_error": row.get("quote_error"),
            "quote_fetched_at": row.get("quote_fetched_at"),
            "quote_as_of": row.get("quote_as_of"),
            "quote_kind": row.get("quote_kind"),
            "quote_attempted_at": row.get("quote_attempted_at"),
            "quote_fallback_reason": row.get("quote_fallback_reason"),
            "history_status": row.get("history_status"),
            "history_error": row.get("history_error"),
            "history_fetched_at": row.get("history_fetched_at"),
            "history_source": row.get("history_source"),
        }
        for row in snapshots.values()
    ]
    return {
        "status": "unavailable" if store_error or fx_store_error else "ok",
        "store_error": store_error or fx_store_error,
        "assets": assets,
        "fx": [
            {
                "pair": row.get("pair"),
                "status": row.get("status"),
                "source": row.get("source"),
                "error": row.get("error"),
                "fetched_at": row.get("fetched_at"),
                "as_of": row.get("as_of"),
                "kind": row.get("kind"),
            }
            for row in fx_snapshots.values()
        ],
    }
