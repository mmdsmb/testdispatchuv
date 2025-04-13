from datetime import datetime
from pydantic import BaseModel

class ItemBase(BaseModel):
    name: str

class ItemCreate(ItemBase):
    pass

class ItemUpdate(ItemBase):
    pass

class Item(ItemBase):
    id: int
    updated_at: datetime

    class Config:
        from_attributes = True 