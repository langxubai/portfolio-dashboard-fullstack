from fastapi import APIRouter, HTTPException
from typing import List
from src.database import supabase
from src.schemas.assets import AssetCreate, AssetResponse

router = APIRouter(
    prefix="/api/assets",
    tags=["Assets"]
)

@router.post("/", response_model=AssetResponse, status_code=201)
def create_asset(asset: AssetCreate):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    data, count = supabase.table("assets").insert(asset.model_dump()).execute()
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
