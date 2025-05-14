import os
from dotenv import load_dotenv
from app.models.hotes_old import HotesSync
from app.core.config import get_settings
import asyncio

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

async def main():
    # Vérifier que les variables d'environnement sont bien chargées
    if not os.getenv('SUPABASE_URL') or not os.getenv('SUPABASE_KEY'):
        raise ValueError("SUPABASE_URL et SUPABASE_KEY doivent être définis dans le fichier .env")
        
    settings = get_settings()
    sync = HotesSync()
    # Le file_id sera automatiquement récupéré depuis HOTES_FILE_ID dans .env
    
    result = await sync.sync(settings.HOTES_FILE_ID,auto_apply=True)
    print(result)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())