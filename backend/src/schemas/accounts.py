from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class AccountBase(BaseModel):
    name: str
    currency: str

class AccountCreate(AccountBase):
    pass

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None

class AccountResponse(AccountBase):
    id: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
