from typing import List, Dict, Any, Optional
from supabase import create_client, Client
from app.core.config import settings
from app.db.base import DataSource

class SupabaseDataSource(DataSource):
    """Implémentation Supabase de l'interface DataSource."""
    
    def __init__(self):
        self.client: Optional[Client] = None
    
    async def connect(self) -> None:
        """Établit la connexion à Supabase."""
        self.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    
    async def disconnect(self) -> None:
        """Ferme la connexion à Supabase."""
        self.client = None
    
    async def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Exécute une requête SQL sur Supabase."""
        if not self.client:
            raise RuntimeError("La connexion à Supabase n'est pas établie")
        
        response = self.client.table("items").select("*").execute()
        return response.data
    
    async def execute_transaction(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Exécute une transaction SQL sur Supabase."""
        if not self.client:
            raise RuntimeError("La connexion à Supabase n'est pas établie")
        
        results = []
        for query in queries:
            # Note: Supabase ne supporte pas directement les transactions SQL brutes
            # Nous exécutons les requêtes séquentiellement
            response = self.client.rpc("execute_sql", {"query": query}).execute()
            results.append(response.data)
        return results
    
    async def health_check(self) -> bool:
        """Vérifie si la connexion à Supabase est active."""
        try:
            if not self.client:
                return False
            # Exécute une requête simple pour vérifier la connexion
            self.client.table("items").select("count").limit(1).execute()
            return True
        except Exception:
            return False 