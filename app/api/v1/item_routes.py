from fastapi import APIRouter, Query, Depends, HTTPException
from app.models.item import ItemCreate
from app.services.item import ItemService
from app.db.item_repo import get_engine, get_db
from sqlalchemy import text
from sqlalchemy.orm import Session
import traceback
from datetime import datetime
import psycopg
import os
from app.db.postgres import PostgresDataSource
from typing import Dict, Any
import logging
from app.core.logger import setup_logger

# Configurez le logger pour ce module
logger = setup_logger(__name__)
logger.setLevel(logging.DEBUG)  # Niveau DEBUG pour capturer tous les détails

# Format des logs (ajoute l'heure, le nom du module et le niveau)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Handler pour écrire dans un fichier (optionnel)
file_handler = logging.FileHandler('item_routes.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler pour la console (obligatoire pour voir les logs dans Docker)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)

# Endpoint 1: Test de connexion à la base de données
@router.get("/db/health", tags=["database"])
async def check_db_health():
    """
    Vérifie la connexion à la base de données.
    """
    logger.info("Début du test de connexion à la base de données")
    ds = PostgresDataSource()
    try:
        health = await ds.health_check()
        logger.debug(f"Résultat du health_check: {health}")
        await ds.disconnect()
        logger.info("Connexion réussie et fermée")
        return {"status": "success", "health": health}
    except Exception as e:
        logger.error(f"Échec de la connexion : {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint 2: Upsert d'un item
@router.post("/db/items/upsert")
async def upsert_item(name: str, value: int):
    ds = PostgresDataSource()
    try:
        await ds.connect()
        result = await ds.execute_query(
            """
            INSERT INTO test_items (name, value)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET value = EXCLUDED.value
            RETURNING id, name, value
            """,
            (name, value)
        )
        return {"status": "success", "data": result[0]}
    except Exception as e:
        logger.error(f"Erreur: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await ds.disconnect()

