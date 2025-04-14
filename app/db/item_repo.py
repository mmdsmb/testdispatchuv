from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create SQLAlchemy engine
engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def upsert_item_with_sqlalchemy(item_id: int, name: str) -> dict:
    """
    Upsert an item using SQLAlchemy.
    """
    db = SessionLocal()
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
        return dict(result)
    finally:
        db.close()

def upsert_item_with_psycopg2(item_id: int, name: str) -> dict:
    """
    Upsert an item using psycopg2.
    """
    import psycopg2
    from app.core.config import settings
    
    conn = psycopg2.connect(
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