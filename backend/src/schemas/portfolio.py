from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class PortfolioDailyHistory(BaseModel):
    date: str
    total_value: float
    total_cost: float
    net_deposit: float
    return_rate: float
    
class PortfolioHistoryResponse(BaseModel):
    history: List[PortfolioDailyHistory]
    period: str
    data_status: str = "ok"
    warnings: List[str] = Field(default_factory=list)
    data_as_of: Optional[datetime] = None
