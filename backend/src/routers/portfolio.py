from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from src.schemas.portfolio import PortfolioHistoryResponse
from src.services.portfolio_history import calculate_portfolio_history

router = APIRouter(
    prefix="/api/portfolio",
    tags=["Portfolio"]
)

@router.get("/history", response_model=PortfolioHistoryResponse)
def get_portfolio_history(
    period: str = Query("1y", description="Time period: 1mo, 3mo, 6mo, 1y, ytd, max"),
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    base_currency: str = Query("CNY", description="Base currency for aggregation")
):
    try:
        return calculate_portfolio_history(period, account_id, base_currency)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate portfolio history: {str(e)}")
