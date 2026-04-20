from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from src.database import supabase
from src.schemas.transactions import TransactionCreate, TransactionResponse

router = APIRouter(
    prefix="/api/transactions",
    tags=["Transactions"]
)

@router.post("/", response_model=TransactionResponse, status_code=201)
def create_transaction(transaction: TransactionCreate):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    data, count = supabase.table("transactions").insert(transaction.model_dump(mode="json")).execute()
    if not data or not data[1]:
        raise HTTPException(status_code=400, detail="Failed to create transaction")
    return data[1][0]

@router.get("/", response_model=List[TransactionResponse])
def get_transactions(
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    asset_id: Optional[str] = Query(None, description="Filter by asset ID")
):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    query = supabase.table("transactions").select("*")
    if account_id:
        query = query.eq("account_id", account_id)
    if asset_id:
        query = query.eq("asset_id", asset_id)
        
    data, count = query.execute()
    return data[1]

@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(transaction_id: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    data, count = supabase.table("transactions").select("*").eq("id", transaction_id).execute()
    if not data[1]:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return data[1][0]

@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    supabase.table("transactions").delete().eq("id", transaction_id).execute()
    return None
