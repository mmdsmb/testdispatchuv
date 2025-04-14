import pytest
from fastapi.testclient import TestClient
from app.services.item import ItemService
from unittest.mock import patch, MagicMock

def test_upsert_item(client: TestClient):
    """Test the upsert item endpoint"""
    # Test avec un ID test spécifique pour faciliter le nettoyage
    response = client.post(
        "/api/v1/items/upsert?item_id=1",
        json={"name": "Test Item for Supabase"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Test Item for Supabase"
    assert "updated_at" in data

# Tests qui ne nécessitent pas de base de données
def test_sum_endpoint(client: TestClient):
    """Test the sum endpoint"""
    response = client.get("/api/v1/sum?a=3&b=5")
    assert response.status_code == 200
    assert response.json() == {"result": 8}

def test_multiply_endpoint(client: TestClient):
    """Test the multiply endpoint"""
    response = client.get("/api/v1/multiply?a=2&b=5")
    assert response.status_code == 200
    assert response.json() == {"result": 10}

# Test unitaire avec mock pour ItemService
@pytest.mark.skip(reason="Exemple de test avec mock - à implémenter si nécessaire")
def test_item_service_with_mock():
    """Test ItemService with mocked database functions"""
    with patch('app.db.item_repo.upsert_item_with_sqlalchemy') as mock_sqlalchemy:
        mock_sqlalchemy.return_value = {"id": 1, "name": "Mocked Item", "updated_at": "2023-01-01T00:00:00"}
        
        result = ItemService.upsert_item(1, "Test Item", use_sqlalchemy=True)
        
        assert result["id"] == 1
        assert result["name"] == "Mocked Item"
        mock_sqlalchemy.assert_called_once_with(1, "Test Item") 