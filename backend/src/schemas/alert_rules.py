from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional
from enum import Enum
from decimal import Decimal

class RuleType(str, Enum):
    TARGET_PRICE = "TARGET_PRICE"
    CHANGE_PERCENT = "CHANGE_PERCENT"
    CHANGE_ABS = "CHANGE_ABS"

class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"

class AlertRuleBase(BaseModel):
    asset_id: str
    rule_type: RuleType
    direction: Direction
    target_value: Decimal = Field(..., max_digits=24, decimal_places=8)
    time_window_minutes: Optional[int] = None
    is_active: bool = True
    cooldown_minutes: int = 1440

class AlertRuleCreate(AlertRuleBase):
    pass

class AlertRuleUpdate(BaseModel):
    asset_id: Optional[str] = None
    rule_type: Optional[RuleType] = None
    direction: Optional[Direction] = None
    target_value: Optional[Decimal] = Field(None, max_digits=24, decimal_places=8)
    time_window_minutes: Optional[int] = None
    is_active: Optional[bool] = None
    cooldown_minutes: Optional[int] = None

class AlertRuleResponse(AlertRuleBase):
    id: str
    last_triggered_at: Optional[datetime] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
