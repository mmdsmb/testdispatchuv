import psycopg
from typing import Optional, List, Any, AsyncIterator
from app.core.config import settings
from app.db.base import DataSource
import logging
from app.core.logger import setup_logger

logger = setup_logger(__name__)

class PostgresDataSource(DataSource):
    def __init__(self):
        self.conn: Optional[psycopg.AsyncConnection] = None

    async def connect(self) -> None:
        """Établit une connexion asynchrone."""
        if not self.conn:
            self.conn = await psycopg.AsyncConnection.connect(
                host=settings.SUPABASE_POOLER_HOST,
                port=settings.SUPABASE_POOLER_PORT,
                dbname=settings.SUPABASE_POOLER_DBNAME,
                user=settings.SUPABASE_POOLER_USER,
                password=settings.SUPABASE_POOLER_PASSWORD,
                sslmode=settings.SUPABASE_POOLER_SSLMODE,
                autocommit=True
            )

    async def disconnect(self) -> None:
        """Ferme la connexion."""
        if self.conn:
            await self.conn.close()
            self.conn = None

    async def execute_query(self, query: str, params: Optional[List[Any]] = None) -> List[Any]:
        """Exécute une requête et retourne les résultats si applicables."""
        if not self.conn:
            await self.connect()
        
        async with self.conn.cursor() as cursor:
            await cursor.execute(query, params or [])
            
            # Debug: Affiche l'état de la transaction
            logger.info(f"État avant commit : {self.conn.info.transaction_status}")
            
            if cursor.description is None:
                assert self.conn is not None  # Ajoutez ceci avant le commit
                await self.conn.commit()
                logger.info(f"État après commit : {self.conn.info.transaction_status}")
                return []
            
            results = await cursor.fetchall()
            if "RETURNING" not in query.upper():
                assert self.conn is not None  # Ajoutez ceci avant le commit
                await self.conn.commit()
            return results

    async def execute_transaction(self, queries: list):
        """Exécute plusieurs requêtes dans une transaction."""
        try:
            for query, params in queries:
                await self.execute_query(query, params)
        except Exception:
            await self.conn.rollback()
            raise

    async def health_check(self) -> bool:
        """Vérifie si la connexion est active."""
        try:
            await self.connect()
            async with self.conn.cursor() as cursor:
                await cursor.execute("SELECT version()")
                version = await cursor.fetchone()
                print(f"PostgreSQL Version: {version[0]}")
            return True
        except Exception as e:
            print(f"Health check failed: {e}")
            return False