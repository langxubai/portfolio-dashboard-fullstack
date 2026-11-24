from pydantic import BaseModel
from decimal import Decimal
from typing import Optional
from datetime import datetime

class PositionResponse(BaseModel):
    account_id: str
    asset_id: str
    symbol: str
    name: str
    asset_type: str
    currency: str
    
    total_quantity: Decimal
    average_cost: Decimal
    
    current_price: Optional[Decimal] = None
    previous_close: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    
    unrealized_pnl: Optional[Decimal] = None
    unrealized_pnl_percent: Optional[Decimal] = None
    
    realized_pnl: Optional[Decimal] = None
    realized_pnl_percent: Optional[Decimal] = None
    
    daily_pnl: Optional[Decimal] = None
    daily_pnl_percent: Optional[Decimal] = None

    # Market-data observability. A stale quote may still carry a usable
    # current_price, while unavailable means the position is intentionally
    # excluded from portfolio valuation instead of being treated as zero.
    price_status: str = "unavailable"
    price_source: Optional[str] = None
    price_as_of: Optional[datetime] = None
    price_market_time: Optional[str] = None
    price_fetched_at: Optional[datetime] = None
    price_kind: Optional[str] = None
    price_fallback_reason: Optional[str] = None
    price_is_stale: bool = False
    price_error: Optional[str] = None
