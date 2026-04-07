from pydantic import BaseModel
from typing import List
from datetime import date

class PortfolioDailyHistory(BaseModel):
    date: str
    total_value: float
    total_cost: float
    net_deposit: float
    return_rate: float
    
class PortfolioHistoryResponse(BaseModel):
    history: List[PortfolioDailyHistory]
    period: str
