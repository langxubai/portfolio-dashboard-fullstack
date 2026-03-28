from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from src.schemas.positions import PositionResponse
from src.services.positions import calculate_positions

router = APIRouter(
    prefix="/api/positions",
    tags=["Positions"]
)

@router.get("/", response_model=List[PositionResponse])
def get_positions(account_id: Optional[str] = Query(None, description="Filter by account ID")):
    try:
        return calculate_positions(account_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate positions: {str(e)}")
