import pytest
from fastapi.testclient import TestClient
from app.services.item import ItemService

def test_upsert_item(client: TestClient):
    """Test the upsert item endpoint"""
    response = client.post(
        "/api/v1/items/upsert?item_id=1",
        json={"name": "Test Item"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Test Item"
    assert "updated_at" in data

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