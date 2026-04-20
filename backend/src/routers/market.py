from fastapi import APIRouter, Query
from typing import List, Dict
from src.services.market_data import get_exchange_rates

router = APIRouter(
    prefix="/api/market",
    tags=["Market Data"]
)

@router.get("/exchange-rates", response_model=Dict[str, float])
def get_rates(
    base: str = Query(..., description="Base currency (e.g. CNY)"),
    targets: List[str] = Query(..., description="List of target currencies to get rates for")
):
    """
    Get exchange rates to a base currency.
    Returns a dictionary of target: rate, where 1 target = rate * base.
    """
    return get_exchange_rates(base=base, targets=targets)
