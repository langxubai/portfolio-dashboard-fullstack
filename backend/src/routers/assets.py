from fastapi import APIRouter, HTTPException
from typing import List
from src.database import supabase
from src.schemas.assets import AssetCreate, AssetResponse, CustomAssetPriceCreate, CustomAssetPriceResponse
import datetime

router = APIRouter(
    prefix="/api/assets",
    tags=["Assets"]
)

@router.post("/", response_model=AssetResponse, status_code=201)
def create_asset(asset: AssetCreate):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
    try:
        data, count = supabase.table("assets").insert(asset.model_dump()).execute()
    except Exception as e:
        err_str = str(e)
        if "23505" in err_str or "duplicate key" in err_str.lower():
            raise HTTPException(
                status_code=400,
                detail=f"资产代码 '{asset.symbol}' 已存在。如需在多个账户持有同一资产，请先到数据库移除 assets 表 symbol 字段的唯一约束（UNIQUE constraint），详见说明。"
            )
        raise HTTPException(status_code=500, detail=f"Failed to create asset: {err_str}")
    if not data or not data[1]:
        raise HTTPException(status_code=400, detail="Failed to create asset")
    return data[1][0]

@router.get("/", response_model=List[AssetResponse])
def get_assets():
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    data, count = supabase.table("assets").select("*").execute()
    return data[1]

@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    data, count = supabase.table("assets").select("*").eq("id", asset_id).execute()
    if not data[1]:
        raise HTTPException(status_code=404, detail="Asset not found")
    return data[1][0]

@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    supabase.table("assets").delete().eq("id", asset_id).execute()
    return None

@router.post("/{asset_id}/prices", response_model=CustomAssetPriceResponse, status_code=201)
def create_custom_asset_price(asset_id: str, price_data: CustomAssetPriceCreate):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    db_data = {
        "asset_id": asset_id,
        "price": price_data.price,
    }
    if price_data.recorded_at:
        db_data["recorded_at"] = price_data.recorded_at.isoformat()

    data, count = supabase.table("custom_asset_prices").insert(db_data).execute()
    if not data or not data[1]:
        raise HTTPException(status_code=400, detail="Failed to record custom asset price")
    return data[1][0]

@router.get("/{asset_id}/prices", response_model=List[CustomAssetPriceResponse])
def get_custom_asset_prices(asset_id: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    data, count = supabase.table("custom_asset_prices").select("*").eq("asset_id", asset_id).order("recorded_at", desc=True).execute()
    return data[1]
