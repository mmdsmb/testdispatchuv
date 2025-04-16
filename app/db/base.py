from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import pytest_asyncio
from supabase import Client  # Pour les assertions de type

class DataSource(ABC):
    """Interface de base pour les sources de données."""
    
    @abstractmethod
    async def connect(self) -> None:
        """Établit la connexion à la source de données."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Ferme la connexion à la source de données."""
        pass
    
    @abstractmethod
    async def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Exécute une requête SQL et retourne les résultats."""
        pass
    
    @abstractmethod
    async def execute_transaction(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Exécute une transaction SQL sur Supabase."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Vérifie si la connexion à la source de données est active."""
        pass 