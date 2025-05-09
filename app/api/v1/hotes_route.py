# Exemple d'utilisation dans un endpoint FastAPI
from fastapi import APIRouter, HTTPException
from app.models.hotes import HotesSync

router = APIRouter()

@router.post("/sync-hotes")
async def sync_hotes(file_id: str, auto_apply: bool = False):
    try:
        sync = HotesSync()
        result = await sync.sync(file_id, auto_apply)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
