#!/usr/bin/env python3
import sys
import argparse
import os
from urllib.parse import urlparse
from dotenv import load_dotenv
import socket  # Pour forcer IPv6

# Utiliser psycopg[binary] (compatible avec psycopg3)
import psycopg

# Charger les variables d'environnement
load_dotenv()

def test_connection(host, port, dbname, user, password, use_ip=False, force_ipv6=False):
    """Test the connection to a PostgreSQL database."""
    print(f"Testing connection to PostgreSQL database...")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Database: {dbname}")
    print(f"User: {user}")
    
    # Désactiver SSL pour simplifier la connexion
    os.environ["PGSSLMODE"] = "disable"
    
    try:
        # Forcer la résolution DNS en IPv6 si demandé
        if force_ipv6:
            host = socket.getaddrinfo(host, port, family=socket.AF_INET6)[0][4][0]
        
        # Construire l'URL de connexion
        conninfo = f"host={host} port={port} dbname={dbname} user={user} password={password}"
        
        # Tenter la connexion
        print("\nTrying connection...")
        conn = psycopg.connect(conninfo)
        
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
        print(f"Connection failed: {e}")
        return False

def test_supabase_connection(supabase_url=None, supabase_key=None, force_ipv6=False):
    """Test the connection to a Supabase database using the Supabase URL and key."""
    # Utiliser les variables d'environnement si non fournies
    if supabase_url is None:
        supabase_url = os.getenv("SUPABASE_URL")
    if supabase_key is None:
        supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("Error: Supabase URL and key not found in environment variables")
        return False
    
    print(f"Testing connection to Supabase database...")
    print(f"Supabase URL: {supabase_url}")
    
    try:
        # Extraire les informations de connexion de l'URL Supabase
        parsed_url = urlparse(supabase_url)
        host = parsed_url.netloc
        if ":" in host:
            host, port = host.split(":")
            port = int(port)
        else:
            port = 5432
        
        # Forcer la résolution DNS en IPv6 si demandé
        if force_ipv6:
            host = socket.getaddrinfo(host, port, family=socket.AF_INET6)[0][4][0]
        
        # Construire l'URL de connexion
        conninfo = f"host={host} port={port} dbname=postgres user=postgres password={supabase_key}"
        
        # Tenter la connexion
        print("\nTrying connection to Supabase...")
        conn = psycopg.connect(conninfo)
        
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
        print(f"Connection failed: {e}")
        return False

def test_pooler_connection(pooler_url, password, force_ipv6=False):
    """Teste la connexion via le Pooler Supabase."""
    print("Testing connection to Supabase Pooler...")
    
    try:
        # Extraire les composants de l'URL
        parsed_url = urlparse(pooler_url)
        host = parsed_url.hostname
        port = parsed_url.port or 5432
        user = parsed_url.username
        dbname = parsed_url.path.lstrip('/') or "postgres"

        # Forcer IPv6 si demandé
        if force_ipv6:
            host = socket.getaddrinfo(host, port, family=socket.AF_INET6)[0][4][0]

        # Construire la chaîne de connexion
        conninfo = f"host={host} port={port} dbname={dbname} user={user} password={password}"

        # Établir la connexion
        print("\nConnecting to Pooler...")
        conn = psycopg.connect(conninfo)

        # Tester la connexion
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()
            print(f"PostgreSQL version: {version[0]}")

            # Vérifier la table 'items'
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
        print(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test PostgreSQL connection')
    parser.add_argument('--host', help='Database host')
    parser.add_argument('--port', default='5432', help='Database port')
    parser.add_argument('--dbname', help='Database name')
    parser.add_argument('--user', help='Database user')
    parser.add_argument('--password', help='Database password')
    parser.add_argument('--ip', action='store_true', help='Use IP address instead of hostname')
    parser.add_argument('--supabase-url', help='Supabase URL (overrides .env)')
    parser.add_argument('--supabase-key', help='Supabase key (overrides .env)')
    parser.add_argument('--use-env', action='store_true', help='Use environment variables from .env file')
    parser.add_argument('--ipv6', action='store_true', help='Force IPv6 resolution')
    parser.add_argument('--pooler-url', help='Supabase Pooler URL (e.g., postgresql://user@host:port/db)')
    parser.add_argument('--pooler-password', help='Database password for Pooler')
    
    args = parser.parse_args()
    
    # Si l'option --use-env est spécifiée, utiliser les variables d'environnement
    if args.use_env:
        # Vérifier si nous avons une URL de pooler dans les variables d'environnement
        pooler_url = os.getenv("SUPABASE_POOLER_URL")
        pooler_password = os.getenv("SUPABASE_POOLER_PASSWORD")
        
        if pooler_url and pooler_password:
            # Utiliser le pooler si disponible
            success = test_pooler_connection(pooler_url, pooler_password, force_ipv6=args.ipv6)
        else:
            # Sinon, utiliser la connexion Supabase standard
            success = test_supabase_connection(force_ipv6=args.ipv6)
    # Si les arguments du pooler sont fournis, utiliser le pooler
    elif args.pooler_url and args.pooler_password:
        success = test_pooler_connection(args.pooler_url, args.pooler_password, force_ipv6=args.ipv6)
    # Si les arguments Supabase sont fournis, utiliser la fonction Supabase
    elif args.supabase_url and args.supabase_key:
        success = test_supabase_connection(args.supabase_url, args.supabase_key, force_ipv6=args.ipv6)
    # Sinon, utiliser la fonction standard
    elif args.host and args.dbname and args.user and args.password:
        success = test_connection(
            args.host, 
            args.port, 
            args.dbname, 
            args.user, 
            args.password,
            args.ip,
            force_ipv6=args.ipv6
        )
    else:
        print("Error: Either provide Supabase URL and key, database connection details, pooler URL and password, or use --use-env")
        sys.exit(1)
    
    if success:
        print("\nConnection test PASSED!")
        sys.exit(0)
    else:
        print("\nConnection test FAILED!")
        sys.exit(1) 