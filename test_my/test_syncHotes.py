from app.models.hotes import HotesSync
from app.core.config import get_settings
import asyncio

async def main():
    settings = get_settings()
    sync = HotesSync()
    # Le file_id sera automatiquement récupéré depuis HOTES_FILE_ID dans .env
    
    result = await sync.sync(settings.HOTES_FILE_ID,auto_apply=True)
    print(result)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())