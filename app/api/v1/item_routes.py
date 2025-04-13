from fastapi import APIRouter, Query
from app.models.item import ItemCreate
from app.services.item import ItemService

router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)

@router.post("/upsert")
async def upsert_item(item: ItemCreate, item_id: int = Query(..., description="The ID of the item")):
    """
    Upsert an item (create if not exists, update if exists).
    
    Example:
    ```json
    {
        "name": "Test Item"
    }
    ```
    """
    result = ItemService.upsert_item(item_id=item_id, name=item.name)
    return result 