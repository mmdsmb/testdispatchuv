import pytest
import os
from sqlalchemy import text

def test_database_connection(test_db):
    """Test que la connexion à la base de données fonctionne dans tous les environnements"""
    result = test_db.execute(text("SELECT 1 AS test")).fetchone()
    assert result[0] == 1
    
    # Vérifier la création et suppression d'un élément de test
    test_db.execute(
        text("INSERT INTO items (id, name) VALUES (:id, :name)"),
        {"id": 999, "name": "Test Database Connection"}
    )
    test_db.commit()
    
    result = test_db.execute(
        text("SELECT name FROM items WHERE id = 999")
    ).fetchone()
    
    assert result[0] == "Test Database Connection"
    
    # Nettoyer
    test_db.execute(text("DELETE FROM items WHERE id = 999"))
    test_db.commit() 