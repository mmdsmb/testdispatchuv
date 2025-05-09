from fastapi import APIRouter, HTTPException
from app.models.chauffeur_bronze import ChauffeurBronzeSync
from fastapi import Depends
from functools import lru_cache
import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    chauffeurs_file_id: str

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

router = APIRouter(
    prefix="/chauffeurs",
    tags=["chauffeurs"]
)

@router.post("/sync-bronze")
async def sync_chauffeurs_bronze(
    file_id: str = Depends(lambda: get_settings().CHAUFFEURS_FILE_ID),
    auto_apply: bool = False
):
    """
    Synchronise les données des chauffeurs depuis un fichier Google Drive vers Supabase
    
    Args:
        file_id: ID du fichier Google Drive (récupéré depuis .env par défaut)
        auto_apply: Si True, applique directement les changements. Sinon, retourne un rapport.
    """
    try:
        sync = ChauffeurBronzeSync()
        result = await sync.sync(file_id, auto_apply)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
