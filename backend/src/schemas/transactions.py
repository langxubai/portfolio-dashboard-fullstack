from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional
from enum import Enum
from decimal import Decimal

class TradeType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"

class TransactionBase(BaseModel):
    account_id: str
    asset_id: str
    trade_type: TradeType
    price: Decimal = Field(..., max_digits=18, decimal_places=4)
    quantity: Decimal = Field(..., max_digits=18, decimal_places=4)
    trade_time: datetime

class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(BaseModel):
    account_id: Optional[str] = None
    asset_id: Optional[str] = None
    trade_type: Optional[TradeType] = None
    price: Optional[Decimal] = Field(None, max_digits=18, decimal_places=4)
    quantity: Optional[Decimal] = Field(None, max_digits=18, decimal_places=4)
    trade_time: Optional[datetime] = None

class TransactionResponse(TransactionBase):
    id: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
