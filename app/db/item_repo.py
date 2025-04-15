import os
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import create_engine, text, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings, IN_CI, IN_DOCKER, SUPABASE_KNOWN_IPS

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

# Variable qui stockera l'URL de connexion qui a fonctionné au démarrage
SUCCESS_CONNECTION_URL = None

def get_engine():
    global _engine
    if _engine is None:
        try:
            # Importer le moteur global depuis main.py
            from app.main import GLOBAL_ENGINE
            if GLOBAL_ENGINE is not None:
                print("Utilisation du moteur global défini dans main.py")
                _engine = GLOBAL_ENGINE
                return _engine
            
            # Si le moteur global n'est pas disponible, essayer de créer un nouveau moteur
            print("Moteur global non disponible, création d'un nouveau moteur")
            
            # Vérifier si nous avons déjà une URL de connexion qui fonctionne
            if SUCCESS_CONNECTION_URL:
                print(f"Utilisation de l'URL de connexion qui a fonctionné au démarrage: {SUCCESS_CONNECTION_URL.replace(settings.DB_PASSWORD, '********')}")
                
                # Options de connexion de base, compatibles avec toutes les versions
                connect_args = {
                    "connect_timeout": 30,
                    "application_name": "FastAPI App",
                    "sslmode": "disable",
                }
                
                # Utiliser l'URL qui a fonctionné
                _engine = create_engine(
                    SUCCESS_CONNECTION_URL,
                    connect_args=connect_args,
                    pool_pre_ping=True
                )
                
                print(f"Moteur SQLAlchemy initialisé avec URL précédemment validée")
                return _engine
            
            # Si nous n'avons pas d'URL prévalidée, essayer différentes options comme avant
            print("Aucune URL prévalidée disponible, tentative manuelle de connexion")
            
            # Options de connexion de base, compatibles avec toutes les versions
            connect_args = {
                "connect_timeout": 10,
                "application_name": "FastAPI App",
                "sslmode": "disable",
            }
            
            # Configurer des paramètres différents selon l'environnement
            if IN_DOCKER:
                print("Exécution dans un environnement Docker")
                
                # Dans Docker, utiliser directement l'adresse IP au lieu du nom d'hôte
                db_uri = settings.SQLALCHEMY_DATABASE_URL
                
                # Si l'URI contient le nom de domaine Supabase, le remplacer par l'IP
                if settings.DB_HOST in SUPABASE_KNOWN_IPS:
                    ip = SUPABASE_KNOWN_IPS[settings.DB_HOST][0]
                    db_uri = db_uri.replace(settings.DB_HOST, ip)
                    print(f"URI remplacée avec IP directe: {db_uri.replace(settings.DB_PASSWORD, '********')}")
                
                # Dans Docker, utiliser les options les plus basiques pour maximiser la compatibilité
                _engine = create_engine(
                    db_uri,
                    connect_args=connect_args,
                    pool_pre_ping=True
                )
            else:
                # En dehors de Docker, on peut ajouter plus d'options
                _engine = create_engine(
                    settings.SQLALCHEMY_DATABASE_URL,
                    connect_args=connect_args,
                    pool_pre_ping=True
                )
            
            # En environnement CI ou Docker, créer les tables au démarrage
            if IN_CI or IN_DOCKER:
                print("Création automatique des tables dans l'environnement CI/Docker")
                Base.metadata.create_all(bind=_engine)
                
        except Exception as e:
            print(f"Erreur lors de l'initialisation du moteur SQLAlchemy: {e}")
            # En cas d'échec, utiliser SQLite en mémoire
            print("Utilisation du moteur SQLite fallback")
            _engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(bind=_engine)
    
    return _engine

def get_session_local():
    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal

def get_db():
    db = get_session_local()
    try:
        yield db
    finally:
        db.close()

def upsert_item_with_sqlalchemy(item_id: int, name: str) -> dict:
    """
    Upsert an item using SQLAlchemy.
    
    Args:
        item_id: The ID of the item
        name: The name of the item
        
    Returns:
        dict: The upserted item
    """
    db = get_session_local()
    try:
        # Vérifier si l'item existe déjà
        item = db.query(Item).filter(Item.id == item_id).first()
        
        if item:
            # Mettre à jour l'item existant
            item.name = name
            item.updated_at = datetime.utcnow()
        else:
            # Créer un nouvel item
            item = Item(id=item_id, name=name)
            db.add(item)
        
        # Sauvegarder les changements
        db.commit()
        db.refresh(item)
        
        # Convertir en dictionnaire
        result = {
            "id": item.id,
            "name": item.name,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None
        }
        
        return result
        
    except Exception as e:
        db.rollback()
        print(f"Erreur lors de l'upsert avec SQLAlchemy: {e}")
        raise
    finally:
        db.close()

def upsert_item_with_psycopg(item_id: int, name: str) -> dict:
    """
    Upsert an item using psycopg directly.
    
    Args:
        item_id: The ID of the item
        name: The name of the item
        
    Returns:
        dict: The upserted item
    """
    engine = get_engine()
    try:
        with engine.connect() as conn:
            # Vérifier si la table existe
            try:
                conn.execute(text("SELECT 1 FROM items LIMIT 1"))
            except Exception as e:
                print(f"La table items n'existe pas: {e}")
                # Créer la table si elle n'existe pas
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS items (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.commit()
            
            # Upsert l'item
            result = conn.execute(
                text("""
                    INSERT INTO items (id, name, updated_at)
                    VALUES (:id, :name, CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO UPDATE
                    SET name = :name, updated_at = CURRENT_TIMESTAMP
                    RETURNING id, name, updated_at
                """),
                {"id": item_id, "name": name}
            ).fetchone()
            
            conn.commit()
            
            if result:
                return {
                    "id": result[0],
                    "name": result[1],
                    "updated_at": result[2].isoformat() if result[2] else None
                }
            else:
                return {"error": "Failed to upsert item"}
                
    except Exception as e:
        print(f"Erreur lors de l'upsert avec psycopg: {e}")
        raise 