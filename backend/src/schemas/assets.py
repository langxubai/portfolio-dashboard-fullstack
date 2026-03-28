from pydantic import BaseModel, ConfigDict
from datetime import datetime

class AssetBase(BaseModel):
    symbol: str
    name: str
    asset_type: str

class AssetCreate(AssetBase):
    pass

class AssetResponse(AssetBase):
    id: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
