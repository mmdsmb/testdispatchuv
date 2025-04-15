import os
import sys
import psycopg2
from psycopg2 import sql
from app.core.config import settings

def test_connection():
    """Test the connection to the Supabase database."""
    print("Testing connection to Supabase database...")
    print(f"Host: {settings.DB_HOST}")
    print(f"Port: {settings.DB_PORT}")
    print(f"Database: {settings.DB_NAME}")
    print(f"User: {settings.DB_USER}")
    
    # Désactiver SSL pour simplifier la connexion
    os.environ["PGSSLMODE"] = "disable"
    
    try:
        # Tenter la connexion avec le nom d'hôte
        print("\nTrying connection with hostname...")
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            database=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            connect_timeout=10
        )
        
        # Si la connexion réussit, exécuter une requête simple
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()
            print(f"Connection successful! PostgreSQL version: {version[0]}")
            
            # Vérifier si la table items existe
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'items'
                )
            """)
            table_exists = cur.fetchone()[0]
            print(f"Table 'items' exists: {table_exists}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Connection failed with hostname: {e}")
        
        # Essayer avec l'IP directe si disponible
        if settings.DB_HOST in settings.SUPABASE_KNOWN_IPS:
            ip = settings.SUPABASE_KNOWN_IPS[settings.DB_HOST][0]
            print(f"\nTrying connection with direct IP: {ip}")
            
            try:
                conn = psycopg2.connect(
                    host=ip,
                    port=settings.DB_PORT,
                    database=settings.DB_NAME,
                    user=settings.DB_USER,
                    password=settings.DB_PASSWORD,
                    connect_timeout=10
                )
                
                with conn.cursor() as cur:
                    cur.execute("SELECT version();")
                    version = cur.fetchone()
                    print(f"Connection successful with IP! PostgreSQL version: {version[0]}")
                
                conn.close()
                return True
                
            except Exception as ip_e:
                print(f"Connection failed with IP: {ip_e}")
        
        return False

if __name__ == "__main__":
    success = test_connection()
    if success:
        print("\nConnection test PASSED!")
        sys.exit(0)
    else:
        print("\nConnection test FAILED!")
        sys.exit(1) 