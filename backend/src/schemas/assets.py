from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class AssetBase(BaseModel):
    symbol: str
    name: str
    asset_type: str

class AssetCreate(AssetBase):
    pass

class AssetUpdate(BaseModel):
    symbol: Optional[str] = None
    name: Optional[str] = None
    asset_type: Optional[str] = None

class AssetResponse(AssetBase):
    id: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
