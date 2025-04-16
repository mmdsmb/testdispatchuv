import psycopg
from typing import Optional, List, Any, AsyncIterator
from app.core.config import settings
from app.db.base import DataSource

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
                sslmode=settings.SUPABASE_POOLER_SSLMODE
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
            
            # Vérifie si la requête produit des résultats
            if cursor.description is None:
                return []
            
            try:
                return await cursor.fetchall()
            except psycopg.ProgrammingError:
                # Pour les requêtes comme INSERT/UPDATE/DELETE avec RETURNING
                if "RETURNING" in query.upper():
                    return await cursor.fetchall()
                return []

    async def execute_transaction(self, queries: List[str]) -> List[List[Any]]:
        """Exécute une série de requêtes dans une transaction et retourne les résultats."""
        if not self.conn:
            await self.connect()
        
        results = []
        async with self.conn.transaction():
            for query in queries:
                async with self.conn.cursor() as cursor:
                    await cursor.execute(query)
                    try:
                        if cursor.description:  # Si la requête retourne des résultats
                            results.append(await cursor.fetchall())
                        else:
                            results.append([])
                    except psycopg.ProgrammingError:
                        if "RETURNING" in query.upper():
                            results.append(await cursor.fetchall())
                        else:
                            results.append([])
        return results

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