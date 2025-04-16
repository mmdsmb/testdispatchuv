import pytest
import pytest_asyncio
import asyncio
from app.db.postgres import PostgresDataSource
from app.core.config import settings

@pytest_asyncio.fixture
async def postgres_ds():
    """Fixture pour initialiser/fermer PostgresDataSource"""
    ds = PostgresDataSource()
    await ds.connect()
    yield ds
    await ds.disconnect()

@pytest.mark.asyncio
async def test_connection(postgres_ds):
    """Teste la connexion à PostgreSQL"""
    is_healthy = await postgres_ds.health_check()
    assert is_healthy, "La connexion à PostgreSQL a échoué"

@pytest.mark.asyncio
async def test_execute_query(postgres_ds):
    """Teste l'exécution d'une requête simple"""
    # Crée une table temporaire si elle n'existe pas
    result = await postgres_ds.execute_query("""
        CREATE TABLE IF NOT EXISTS test_items (
            id SERIAL PRIMARY KEY,
            name TEXT
        )
    """)
    assert result == [], "La création de table ne devrait pas retourner de résultats"
    
    # Teste une requête SELECT
    result = await postgres_ds.execute_query("SELECT * FROM test_items")
    assert isinstance(result, list), "Le résultat devrait être une liste"

@pytest.mark.asyncio
async def test_transaction(postgres_ds):
    """Teste une transaction avec plusieurs requêtes"""
    # Crée la table si elle n'existe pas
    await postgres_ds.execute_query("""
        CREATE TABLE IF NOT EXISTS test_items (
            id SERIAL PRIMARY KEY,
            name TEXT
        )
    """)
    
    # queries = [
    #     "INSERT INTO test_items (name) VALUES ('Item 1')",
    #     "SELECT * FROM test_items WHERE name = 'Item 1'",
    #     "DELETE FROM test_items WHERE name = 'Item 1' RETURNING *"
    # ]
    queries = [
        "INSERT INTO test_items (name) VALUES ('Item 1')",
        "SELECT * FROM test_items WHERE name = 'Item 1'",
        "INSERT INTO test_items (name) VALUES ('Item 2')"
    ]
    
    results = await postgres_ds.execute_transaction(queries)
    assert len(results) == 3, "3 résultats attendus (insert, select, delete)" 