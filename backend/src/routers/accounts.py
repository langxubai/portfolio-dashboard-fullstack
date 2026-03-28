from fastapi import APIRouter, HTTPException
from typing import List
from src.database import supabase
from src.schemas.accounts import AccountCreate, AccountResponse

router = APIRouter(
    prefix="/api/accounts",
    tags=["Accounts"]
)

@router.post("/", response_model=AccountResponse, status_code=201)
def create_account(account: AccountCreate):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized. Check .env configuration.")
        
    data, count = supabase.table("accounts").insert(account.model_dump()).execute()
    # Supabase python client returns a raw API response object, where data contains results
    # `data` structure depends on the API return usually [ { item } ]
    if not data or not data[1]: # data[1] is the returned record list
        raise HTTPException(status_code=400, detail="Failed to create account")
    return data[1][0]

@router.get("/", response_model=List[AccountResponse])
def get_accounts():
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    data, count = supabase.table("accounts").select("*").execute()
    return data[1]

@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    data, count = supabase.table("accounts").select("*").eq("id", account_id).execute()
    if not data[1]:
        raise HTTPException(status_code=404, detail="Account not found")
    return data[1][0]

@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    supabase.table("accounts").delete().eq("id", account_id).execute()
    return None
