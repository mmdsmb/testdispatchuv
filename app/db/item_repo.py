import os
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, text, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings, IN_CI

# Create Base class for declarative models
Base = declarative_base()

# Define the Item model
class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow)

# Initialisation paresseuse du moteur SQLAlchemy
_engine = None
_SessionLocal = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
        
        # En environnement CI, créer les tables au démarrage
        if IN_CI:
            Base.metadata.create_all(bind=_engine)
            
    return _engine

def get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal

def get_db():
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()

def upsert_item_with_sqlalchemy(item_id: int, name: str) -> dict:
    """
    Upsert an item using SQLAlchemy.
    """
    db = get_session_local()()
    try:
        # Using raw SQL for UPSERT
        query = text("""
            INSERT INTO items (id, name, updated_at)
            VALUES (:id, :name, :updated_at)
            ON CONFLICT (id) DO UPDATE
            SET name = :name, updated_at = :updated_at
            RETURNING id, name, updated_at
        """)
        
        result = db.execute(
            query,
            {
                "id": item_id,
                "name": name,
                "updated_at": datetime.utcnow()
            }
        ).fetchone()
        
        db.commit()
        
        # Traiter le résultat de manière sécurisée
        if result is None:
            return {"id": item_id, "name": name, "updated_at": datetime.utcnow()}
        
        # Convertir en dictionnaire de manière compatible avec psycopg v3
        return {
            "id": result[0] if len(result) > 0 else item_id,
            "name": result[1] if len(result) > 1 else name,
            "updated_at": result[2] if len(result) > 2 else datetime.utcnow()
        }
    finally:
        db.close()

def upsert_item_with_psycopg(item_id: int, name: str) -> dict:
    """
    Upsert an item using psycopg.
    """
    import psycopg
    from app.core.config import settings
    
    conn = psycopg.connect(
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_SERVER
    )
    
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO items (id, name, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET name = %s, updated_at = %s
                RETURNING id, name, updated_at
            """, (item_id, name, datetime.utcnow(), name, datetime.utcnow()))
            
            result = cur.fetchone()
            conn.commit()
            
            return {
                "id": result[0],
                "name": result[1],
                "updated_at": result[2]
            }
    finally:
        conn.close() 