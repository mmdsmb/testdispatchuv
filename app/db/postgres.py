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
            try:
                self.conn = await psycopg.AsyncConnection.connect(
                    host=settings.SUPABASE_POOLER_HOST,
                    port=settings.SUPABASE_POOLER_PORT,
                    dbname=settings.SUPABASE_POOLER_DBNAME,
                    user=settings.SUPABASE_POOLER_USER,
                    password=settings.SUPABASE_POOLER_PASSWORD,
                    sslmode=settings.SUPABASE_POOLER_SSLMODE,
                    autocommit=False  # Désactivé explicitement
                )
                logger.info("Connexion à la base de données établie avec succès")
            except Exception as e:
                logger.error(f"Échec de la connexion : {e}")
                raise

    async def disconnect(self) -> None:
        """Ferme la connexion."""
        if self.conn:
            await self.conn.close()
            self.conn = None

    async def execute_query(self, query: str, params: Optional[List[Any]] = None) -> List[Any]:
        """Exécute une requête unique avec gestion de transaction."""
        # Réutilise execute_transaction pour garantir la cohérence
        return await self.execute_transaction([(query, params)])

    async def execute_transaction(self, queries_with_params: List[tuple]) -> List[Any]:
        """Exécute plusieurs requêtes dans une transaction atomique."""
        if not self.conn:
            await self.connect()
        
        # Résultats de la dernière requête
        final_results = []
        
        try:
            # Début explicite de transaction
            await self.conn.execute("BEGIN")
            logger.info("Transaction démarrée")
            
            async with self.conn.cursor() as cursor:
                for query, params in queries_with_params:
                    # Gestion spéciale pour WITH et requêtes complexes
                    logger.debug(f"Exécution dans transaction: {query}")
                    await cursor.execute(query, params or [])
                    
                    # Capture des résultats si présents
                    if cursor.description is not None:
                        final_results = await cursor.fetchall()
            
            # Commit explicite à la fin de toutes les requêtes
            await self.conn.execute("COMMIT")
            logger.info("Transaction validée avec succès")
            return final_results
        
        except Exception as e:
            # Rollback en cas d'erreur
            logger.error(f"Erreur pendant la transaction: {str(e)}")
            await self.conn.execute("ROLLBACK")
            logger.info("Transaction annulée (rollback)")
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

    async def upsert_item(self, name: str, value: int):
        try:
            await self.connect()
            async with self.conn.transaction():  # <-- Transaction explicite
                result = await self.execute_query(
                    """
                    INSERT INTO test_items (name, value)
                    VALUES (%s, %s)
                    ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value
                    RETURNING id, name, value
                    """,
                    (name, value)
                )
                return {"status": "success", "data": result[0]}
        finally:
            await self.disconnect()  # Fermeture garantie

    async def fetch_all(self, query, params=None):
        """Execute a query and return all rows as a list of dictionaries."""
        if not self.conn:
            await self.connect()
        async with self.conn.cursor() as cursor:
            await cursor.execute(query, params)
            columns = [col.name for col in cursor.description]
            rows = await cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]

    async def fetch_one(self, query: str, params=None):
        """Exécute une requête et retourne une seule ligne."""
        async with self.conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchone()

    async def fetch_one_dict(self, query: str, params=None) -> dict:
        """Exécute une requête et retourne une seule ligne sous forme de dictionnaire."""
        async with self.conn.cursor() as cur:
            await cur.execute(query, params)
            row = await cur.fetchone()
            if not row:
                return None  # Aucune ligne trouvée
            columns = [col.name for col in cur.description]
            return dict(zip(columns, row))

    async def close(self) -> None:
        """Ferme la connexion à la base de données."""
        if hasattr(self, "conn") and self.conn:
            await self.conn.close()
            self.conn = None