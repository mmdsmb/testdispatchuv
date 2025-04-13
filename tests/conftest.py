import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.config import settings

# Create test database engine
TEST_SQLALCHEMY_DATABASE_URL = "postgresql://test:test@localhost:5432/test_db"
engine = create_engine(TEST_SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def test_db():
    # Create tables
    from app.db.item_repo import Base
    Base.metadata.create_all(bind=engine)
    
    yield TestingSessionLocal()
    
    # Drop tables after tests
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    return TestClient(app) 