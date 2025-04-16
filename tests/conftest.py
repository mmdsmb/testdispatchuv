import sys
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging
from app.db.postgres import PostgresDataSource
from datetime import datetime

# Ajouter le répertoire racine au PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app
from app.core.config import settings
from app.db.item_repo import Base

# Détecter si on est dans un environnement CI (GitHub Actions)
IN_CI = os.environ.get("CI") == "true"

# Initialisation globale pour les tests CI
if IN_CI:
    # Format direct pour éviter le problème de chemin absolu avec /test_db
    TEST_SQLALCHEMY_DATABASE_URL = "postgresql://test:test@localhost/test_db"
    
    # Créer le moteur une seule fois pour toute la session de test
    global_engine = create_engine(TEST_SQLALCHEMY_DATABASE_URL)
    
    # Créer toutes les tables au début des tests
    Base.metadata.create_all(bind=global_engine)

@pytest.fixture
def test_engine():
    # En CI, utiliser la config de test PostgreSQL du workflow
    if IN_CI:
        # Utiliser le moteur global déjà créé
        engine = global_engine
    else:
        # En développement, utiliser Supabase
        engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    return engine

@pytest.fixture
def test_db(test_engine):
    from app.db import item_repo
    
    original_engine = getattr(item_repo, '_engine', None)
    item_repo._engine = test_engine
    
    # Create session
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = TestingSessionLocal()
    
    # Nettoyer les données existantes dans la table items
    db.execute(text("DELETE FROM items WHERE id IN (1, 2, 3, 4, 5)"))
    db.commit()
    
    yield db
    
    # Nettoyer les données après les tests
    db.execute(text("DELETE FROM items WHERE id IN (1, 2, 3, 4, 5)"))
    db.commit()
    
    db.close()
    
    # Restore original engine
    item_repo._engine = original_engine

@pytest.fixture
def client():
    return TestClient(app)

# Configurez le logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

@pytest.mark.asyncio
async def test_database_connection():
    """Teste la connexion à Supabase avec PostgresDataSource."""
    logger.info("Début du test de connexion à Supabase")
    ds = PostgresDataSource()
    
    try:
        # Test de connexion basique
        health = await ds.health_check()
        logger.debug(f"Health check: {health}")
        assert health == "Connection healthy"

        # Test CRUD complet
        # 1. Nettoyage initial
        await ds.execute_query("DELETE FROM test_items WHERE name = 'test_connection_item'")
        await ds.execute_query("COMMIT")

        # 2. Insertion
        insert_result = await ds.execute_query(
            "INSERT INTO test_items (name, value) VALUES (%s, %s) RETURNING id",
            ("test_connection_item", 42)
        )
        await ds.execute_query("COMMIT")
        logger.debug(f"Insertion réussie: {insert_result}")
        assert len(insert_result) > 0

        # 3. Vérification
        check_result = await ds.execute_query(
            "SELECT value FROM test_items WHERE name = %s",
            ("test_connection_item",)
        )
        logger.debug(f"Vérification: {check_result}")
        assert check_result[0][0] == 42

    except Exception as e:
        logger.error(f"Échec du test: {str(e)}", exc_info=True)
        await ds.execute_query("ROLLBACK")
        raise
    finally:
        # Nettoyage final même en cas d'échec
        await ds.execute_query("DELETE FROM test_items WHERE name = 'test_connection_item'")
        await ds.execute_query("COMMIT")
        await ds.disconnect()
        logger.info("Connexion fermée")

@pytest.mark.asyncio
async def test_upsert_item():
    """Teste l'endpoint d'upsert avec Supabase."""
    logger.info("Début du test d'upsert")
    ds = PostgresDataSource()
    
    try:
        # 1. Nettoyage initial
        await ds.execute_query("DELETE FROM test_items WHERE name = 'test_upsert_item'")
        await ds.execute_query("COMMIT")

        # 2. Appel API
        response = client.post(
            "/api/v1/items/upsert",
            params={"name": "test_upsert_item", "value": 100}
        )
        logger.debug(f"Réponse API: {response.json()}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # 3. Vérification directe en base
        db_result = await ds.execute_query(
            "SELECT value FROM test_items WHERE name = %s",
            ("test_upsert_item",)
        )
        logger.debug(f"Vérification en base: {db_result}")
        assert db_result[0][0] == 100

    except Exception as e:
        logger.error(f"Échec du test: {str(e)}", exc_info=True)
        await ds.execute_query("ROLLBACK")
        raise
    finally:
        # Nettoyage final
        await ds.execute_query("DELETE FROM test_items WHERE name = 'test_upsert_item'")
        await ds.execute_query("COMMIT")
        await ds.disconnect()
        logger.info("Connexion fermée") 