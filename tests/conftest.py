import sys
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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