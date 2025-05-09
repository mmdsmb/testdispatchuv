# test_my/test_syncChauffeursBronze.py
from app.models.chauffeur_bronze import ChauffeurBronzeSync
from app.core.config import get_settings
import asyncio

async def main():
    settings = get_settings()
    sync = ChauffeurBronzeSync()
    result = await sync.sync(settings.CHAUFFEURS_FILE_ID, auto_apply=True)
    print(result)

if __name__ == "__main__":
    asyncio.run(main())