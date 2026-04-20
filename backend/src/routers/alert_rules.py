from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from src.database import supabase
from src.schemas.alert_rules import AlertRuleCreate, AlertRuleResponse, AlertRuleUpdate

router = APIRouter(
    prefix="/api/alert_rules",
    tags=["Alert Rules"]
)

@router.post("/", response_model=AlertRuleResponse, status_code=201)
def create_alert_rule(alert_rule: AlertRuleCreate):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    data, count = supabase.table("alert_rules").insert(alert_rule.model_dump(mode="json")).execute()
    if not data or not data[1]:
        raise HTTPException(status_code=400, detail="Failed to create alert rule")
    return data[1][0]

@router.get("/", response_model=List[AlertRuleResponse])
def get_alert_rules(
    asset_id: Optional[str] = Query(None, description="Filter by asset ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status")
):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    query = supabase.table("alert_rules").select("*")
    if asset_id:
        query = query.eq("asset_id", asset_id)
    if is_active is not None:
        query = query.eq("is_active", is_active)
        
    data, count = query.execute()
    return data[1]

@router.get("/{rule_id}", response_model=AlertRuleResponse)
def get_alert_rule(rule_id: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    data, count = supabase.table("alert_rules").select("*").eq("id", rule_id).execute()
    if not data[1]:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return data[1][0]

@router.put("/{rule_id}", response_model=AlertRuleResponse)
def update_alert_rule(rule_id: str, alert_rule_update: AlertRuleUpdate):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    update_data = alert_rule_update.model_dump(exclude_unset=True, mode="json")
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")
        
    data, count = supabase.table("alert_rules").update(update_data).eq("id", rule_id).execute()
    if not data or not data[1]:
        raise HTTPException(status_code=404, detail="Alert rule not found or update failed")
    return data[1][0]

@router.delete("/{rule_id}", status_code=204)
def delete_alert_rule(rule_id: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")
        
    supabase.table("alert_rules").delete().eq("id", rule_id).execute()
    return None
