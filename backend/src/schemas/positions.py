from pydantic import BaseModel
from decimal import Decimal
from typing import Optional

class PositionResponse(BaseModel):
    account_id: str
    asset_id: str
    symbol: str
    name: str
    asset_type: str
    
    total_quantity: Decimal
    average_cost: Decimal
    
    current_price: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    
    unrealized_pnl: Optional[Decimal] = None
    unrealized_pnl_percent: Optional[Decimal] = None
