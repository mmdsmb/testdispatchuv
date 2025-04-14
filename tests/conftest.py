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

# Détecter si on est dans un environnement CI (GitHub Actions)
IN_CI = os.environ.get("CI") == "true"

@pytest.fixture
def test_engine():
    # En CI, utiliser la config de test PostgreSQL du workflow
    if IN_CI:
        # Format direct pour éviter le problème de chemin absolu avec /test_db
        TEST_SQLALCHEMY_DATABASE_URL = "postgresql://test:test@localhost/test_db"
        engine = create_engine(TEST_SQLALCHEMY_DATABASE_URL)
    else:
        # En développement, utiliser Supabase
        engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    return engine

@pytest.fixture
def test_db(test_engine):
    from app.db import item_repo
    from app.db.item_repo import Base
    
    original_engine = getattr(item_repo, '_engine', None)
    item_repo._engine = test_engine
    
    # En CI, créer les tables car on part d'une BD vide
    if IN_CI:
        Base.metadata.create_all(bind=test_engine)
    
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
    
    # En CI, supprimer les tables
    if IN_CI:
        Base.metadata.drop_all(bind=test_engine)
    
    db.close()
    
    # Restore original engine
    item_repo._engine = original_engine

@pytest.fixture
def client():
    return TestClient(app) 