from fastapi import APIRouter, Query, Depends
from app.models.item import ItemCreate
from app.services.item import ItemService
from app.db.item_repo import get_engine, get_db
from sqlalchemy import text
from sqlalchemy.orm import Session
import traceback
from datetime import datetime

router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)

@router.post("/upsert", tags=["items"], summary="Upsert an item", response_model=dict)
async def upsert_item(
    item: ItemCreate, 
    item_id: int = Query(..., description="The ID of the item"),
    db: Session = Depends(get_db)
):
    """
    Upsert an item (create if not exists, update if exists).
    
    Example:
    ```json
    {
        "name": "Test Item"
    }
    ```
    """
    # Utiliser directement la connexion à la base de données comme dans pytest
    try:
        # Utiliser le même style de requête que dans les tests
        # Vérifier si l'élément existe
        existing = db.execute(
            text("SELECT id FROM items WHERE id = :id"),
            {"id": item_id}
        ).fetchone()
        
        if existing:
            # Mise à jour si l'élément existe
            result = db.execute(
                text("""
                    UPDATE items 
                    SET name = :name, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    RETURNING id, name, updated_at
                """),
                {"id": item_id, "name": item.name}
            ).fetchone()
        else:
            # Insertion si l'élément n'existe pas
            result = db.execute(
                text("""
                    INSERT INTO items (id, name, updated_at)
                    VALUES (:id, :name, CURRENT_TIMESTAMP)
                    RETURNING id, name, updated_at
                """),
                {"id": item_id, "name": item.name}
            ).fetchone()
            
        db.commit()
        
        # Convertir le résultat en dictionnaire
        if result:
            return {
                "id": result[0],
                "name": result[1],
                "updated_at": result[2]
            }
        else:
            # En cas d'erreur, utiliser la méthode du service (fallback)
            return ItemService.upsert_item(item_id=item_id, name=item.name)
            
    except Exception as e:
        # En cas d'erreur, rollback et utiliser la méthode de service
        db.rollback()
        print(f"Erreur lors de l'upsert direct: {e}")
        return ItemService.upsert_item(item_id=item_id, name=item.name)

@router.get("/check-connection", tags=["database"], summary="Vérifier la connexion à la base de données")
async def check_database_connection():
    """
    Vérifie si la connexion à la base de données fonctionne correctement.
    
    Renvoie des informations sur la connexion et un statut indiquant si elle est active.
    """
    try:
        # Tenter d'obtenir le moteur SQLAlchemy
        engine = get_engine()
        
        # Collecter des informations sur la configuration
        connection_info = {
            "url": str(engine.url).replace(":Ouibamba2025!", ":********"),
            "driver": engine.driver,
            "dialect": engine.dialect.name + (f"+{engine.dialect.driver}" if engine.dialect.driver else ""),
            "pool_size": engine.pool.size(),
            "connect_args": str(getattr(engine.dialect, 'connect_args', {}))
        }
        
        # Exécuter une requête simple
        try:
            with engine.connect() as connection:
                result = connection.execute(text("SELECT 1")).scalar()
                
            return {
                "status": "success",
                "message": "Connexion à la base de données établie avec succès",
                "result": result,
                "connection_info": connection_info
            }
        except Exception as conn_e:
            # Erreur lors de l'exécution de la requête
            error_str = str(conn_e)
            trace = traceback.format_exc()
            return {
                "status": "error",
                "message": "Erreur lors de l'exécution de la requête",
                "error": error_str,
                "traceback": trace,
                "connection_info": connection_info
            }
    except Exception as e:
        # Erreur lors de l'initialisation de la connexion
        error_str = str(e)
        trace = traceback.format_exc()
        return {
            "status": "error",
            "message": "Erreur de connexion à la base de données",
            "error": error_str,
            "traceback": trace
        }
        
@router.get("/test-insert", tags=["database"], summary="Tester l'insertion directe dans la BD")
async def test_insert():
    """
    Tente une insertion directe dans la base de données pour tester la connexion.
    Utilise la méthode la plus simple possible.
    """
    try:
        # Obtenir la connexion
        engine = get_engine()
        
        # Créer la table si elle n'existe pas
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS test_items (
                    id INTEGER PRIMARY KEY,
                    message TEXT,
                    created_at TIMESTAMP
                )
            """))
        
        # Insérer un élément de test
        now = datetime.utcnow()
        test_id = int(now.timestamp())
        
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO test_items (id, message, created_at) VALUES (:id, :msg, :ts)"),
                {"id": test_id, "msg": f"Test connection at {now}", "ts": now}
            )
            
            # Vérifier l'insertion
            result = conn.execute(
                text("SELECT id, message, created_at FROM test_items WHERE id = :id"),
                {"id": test_id}
            ).fetchone()
        
        if result:
            return {
                "status": "success",
                "message": "Insertion réussie dans la base de données",
                "data": {
                    "id": result[0],
                    "message": result[1],
                    "created_at": result[2]
                }
            }
        else:
            return {
                "status": "error",
                "message": "Insertion effectuée mais impossible de récupérer les données"
            }
            
    except Exception as e:
        error_str = str(e)
        trace = traceback.format_exc()
        return {
            "status": "error",
            "message": "Erreur lors du test d'insertion",
            "error": error_str,
            "traceback": trace
        }

@router.get("/test-psycopg", tags=["database"], summary="Tester la connexion avec psycopg directement")
async def test_psycopg():
    """
    Tente une connexion directe à la base de données avec psycopg.
    Cette approche contourne SQLAlchemy complètement.
    """
    try:
        # Tenter d'importer psycopg
        import psycopg
        from app.core.config import settings
        
        connection_params = {
            "user": settings.POSTGRES_USER,
            "password": settings.POSTGRES_PASSWORD, 
            "host": settings.POSTGRES_SERVER,
            "port": 5432,
            "dbname": settings.POSTGRES_DB,
            "connect_timeout": 10
        }
        
        # Journaliser les paramètres (sauf le mot de passe)
        safe_params = connection_params.copy()
        safe_params["password"] = "********"
        
        # Tenter plusieurs approches pour la connexion
        strategies = []
        
        # Stratégie 1: Connexion directe avec les paramètres
        try:
            strategies.append({"name": "direct_params", "status": "attempting"})
            conn = psycopg.connect(**connection_params)
            strategies[-1]["status"] = "success"
            
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
                strategies[-1]["version"] = version
                
                # Tester la table test_items
                try:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS test_items_direct (
                            id INTEGER PRIMARY KEY,
                            message TEXT,
                            created_at TIMESTAMP
                        )
                    """)
                    strategies[-1]["table_create"] = "success"
                    
                    # Insérer un test
                    now = datetime.utcnow()
                    test_id = int(now.timestamp())
                    cur.execute(
                        "INSERT INTO test_items_direct (id, message, created_at) VALUES (%s, %s, %s)",
                        (test_id, f"Test direct psycopg at {now}", now)
                    )
                    conn.commit()
                    strategies[-1]["insert"] = "success"
                    
                    # Lire le test
                    cur.execute("SELECT * FROM test_items_direct WHERE id=%s", (test_id,))
                    row = cur.fetchone()
                    if row:
                        strategies[-1]["read"] = "success"
                        strategies[-1]["data"] = {
                            "id": row[0],
                            "message": row[1],
                            "timestamp": row[2]
                        }
                except Exception as table_e:
                    strategies[-1]["table_error"] = str(table_e)
            
            conn.close()
            
        except Exception as e:
            strategies[-1]["status"] = "failed"
            strategies[-1]["error"] = str(e)
            
        # Stratégie 2: Connexion via une URL
        try:
            strategies.append({"name": "url_connection", "status": "attempting"})
            
            # Construire l'URL manuellement
            url = f"postgres://{connection_params['user']}:{connection_params['password']}@{connection_params['host']}:{connection_params['port']}/{connection_params['dbname']}"
            
            # Tentative de connexion
            conn = psycopg.connect(url)
            strategies[-1]["status"] = "success"
            
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()[0]
                strategies[-1]["result"] = result
                
            conn.close()
        except Exception as e:
            strategies[-1]["status"] = "failed"
            strategies[-1]["error"] = str(e)
        
        # Si au moins une stratégie a réussi
        if any(s["status"] == "success" for s in strategies):
            return {
                "status": "success",
                "message": "Au moins une méthode de connexion a réussi",
                "connection_params": safe_params,
                "strategies": strategies
            }
        else:
            return {
                "status": "error",
                "message": "Toutes les tentatives de connexion ont échoué",
                "connection_params": safe_params,
                "strategies": strategies
            }
    except Exception as e:
        error_str = str(e)
        trace = traceback.format_exc()
        return {
            "status": "error",
            "message": "Erreur générale lors du test psycopg",
            "error": error_str,
            "traceback": trace
        }

@router.get("/diagnostic", tags=["system"], summary="Diagnostic complet du système et de la base de données")
async def system_diagnostic():
    """
    Effectue un diagnostic complet du système et des capacités de connexion à la base de données.
    Renvoie des informations détaillées sur l'environnement, les bibliothèques et les tentatives de connexion.
    """
    import sys
    import platform
    import os
    import socket
    import json
    import traceback
    from app.core.config import settings
    
    result = {
        "system": {
            "platform": platform.platform(),
            "python_version": sys.version,
            "python_path": sys.executable,
            "cwd": os.getcwd(),
            "environment": {k: v for k, v in os.environ.items() if "password" not in k.lower() and "secret" not in k.lower()}
        },
        "network": {
            "hostname": socket.gethostname(),
            "ip": socket.gethostbyname(socket.gethostname()),
        },
        "database_config": {
            "server": settings.POSTGRES_SERVER,
            "db": settings.POSTGRES_DB,
            "user": settings.POSTGRES_USER,
            "sqlalchemy_uri": str(settings.SQLALCHEMY_DATABASE_URI).replace(settings.POSTGRES_PASSWORD, "********") if settings.POSTGRES_PASSWORD else str(settings.SQLALCHEMY_DATABASE_URI),
        },
        "dns_resolution": {},
        "connection_attempts": []
    }
    
    # Test de résolution DNS
    try:
        host = settings.POSTGRES_SERVER
        # Essayer la résolution DNS standard
        try:
            ip_info = socket.getaddrinfo(host, 5432)
            result["dns_resolution"]["standard"] = [
                {"family": info[0], "type": info[1], "proto": info[2], "ip": info[4][0]}
                for info in ip_info
            ]
        except Exception as e:
            result["dns_resolution"]["standard_error"] = str(e)
            
        # Essayer la résolution IPv4 spécifique
        try:
            ipv4_info = socket.getaddrinfo(host, 5432, socket.AF_INET)
            result["dns_resolution"]["ipv4"] = [info[4][0] for info in ipv4_info]
        except Exception as e:
            result["dns_resolution"]["ipv4_error"] = str(e)
        
        # Test de ping
        import subprocess
        try:
            # Exécuter ping avec timeout de 5 secondes
            process = subprocess.run(
                ["ping", "-c", "1", "-W", "5", host],
                capture_output=True,
                text=True,
                timeout=10
            )
            result["dns_resolution"]["ping"] = {
                "command": f"ping -c 1 -W 5 {host}",
                "exit_code": process.returncode,
                "output": process.stdout,
                "error": process.stderr
            }
        except Exception as e:
            result["dns_resolution"]["ping_error"] = str(e)
            
        # Test de port
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            
            # Si nous avons résolu des adresses IPv4, tester la connexion
            if "ipv4" in result["dns_resolution"] and result["dns_resolution"]["ipv4"]:
                ipv4 = result["dns_resolution"]["ipv4"][0]
                connection_result = s.connect_ex((ipv4, 5432))
                result["dns_resolution"]["port_check"] = {
                    "ip": ipv4,
                    "port": 5432,
                    "result_code": connection_result,
                    "is_open": connection_result == 0
                }
            s.close()
        except Exception as e:
            result["dns_resolution"]["port_check_error"] = str(e)
    except Exception as e:
        result["dns_resolution"]["error"] = str(e)
    
    # Test de connexion avec différentes bibliothèques
    
    # 1. SQLAlchemy
    try:
        from sqlalchemy import create_engine, text
        
        result["connection_attempts"].append({
            "method": "sqlalchemy",
            "status": "attempting"
        })
        
        engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI), 
                               connect_args={"connect_timeout": 10})
        with engine.connect() as conn:
            db_version = conn.execute(text("SELECT version()")).scalar()
            result["connection_attempts"][-1].update({
                "status": "success",
                "version": db_version
            })
    except Exception as e:
        result["connection_attempts"][-1].update({
            "status": "failed",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
    
    # 2. psycopg
    try:
        import psycopg
        
        result["connection_attempts"].append({
            "method": "psycopg",
            "status": "attempting"
        })
        
        connection_string = str(settings.SQLALCHEMY_DATABASE_URI).replace("+psycopg", "")
        conn = psycopg.connect(connection_string)
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            result["connection_attempts"][-1].update({
                "status": "success",
                "version": version
            })
        conn.close()
    except Exception as e:
        result["connection_attempts"][-1].update({
            "status": "failed",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
    
    return result

@router.get("/test-direct-ip", tags=["database"], summary="Tester la connexion directement avec l'adresse IP")
async def test_direct_ip():
    """
    Tente une connexion directe à la base de données en utilisant l'adresse IP au lieu du nom de domaine.
    Solution radicale pour les problèmes de DNS dans Docker.
    """
    import psycopg
    import traceback
    from app.core.config import settings, SUPABASE_KNOWN_IPS
    
    # Configuration de l'adresse IP pour Supabase
    ip_address = None
    if "db.zpjemgpnfaeayofvnkzo.supabase.co" in SUPABASE_KNOWN_IPS:
        ip_address = SUPABASE_KNOWN_IPS["db.zpjemgpnfaeayofvnkzo.supabase.co"][0]
    else:
        ip_address = "34.142.230.92"  # Adresse IP de secours
    
    result = {
        "status": "pending",
        "message": f"Tentative de connexion à {ip_address}:5432",
        "connection_params": {
            "host": ip_address,
            "port": 5432,
            "database": settings.POSTGRES_DB,
            "user": settings.POSTGRES_USER,
            "password": "********"  # Masqué pour la sécurité
        },
        "attempts": []
    }
    
    # Tentative 1: URL directe
    try:
        result["attempts"].append({
            "method": "direct_url",
            "status": "attempting"
        })
        
        conn_url = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{ip_address}:5432/{settings.POSTGRES_DB}"
        conn = psycopg.connect(conn_url, sslmode="disable", connect_timeout=10)
        
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            
            # Vérifier aussi la table items
            try:
                cur.execute("SELECT COUNT(*) FROM items")
                count = cur.fetchone()[0]
                result["attempts"][-1]["items_count"] = count
            except Exception as table_e:
                result["attempts"][-1]["table_error"] = str(table_e)
            
        conn.close()
        
        result["attempts"][-1].update({
            "status": "success",
            "version": version
        })
        
        result["status"] = "success"
        result["message"] = f"Connexion réussie à {ip_address}:5432"
        
    except Exception as e:
        result["attempts"][-1].update({
            "status": "failed",
            "error": str(e),
            "traceback": traceback.format_exc()
        })
        
        # Tentative 2: Paramètres individuels
        try:
            result["attempts"].append({
                "method": "individual_params",
                "status": "attempting"
            })
            
            conn = psycopg.connect(
                host=ip_address,
                port=5432,
                dbname=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                connect_timeout=10,
                sslmode="disable"
            )
            
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
            
            conn.close()
            
            result["attempts"][-1].update({
                "status": "success",
                "version": version
            })
            
            result["status"] = "success"
            result["message"] = f"Connexion réussie à {ip_address}:5432 avec paramètres individuels"
            
        except Exception as e2:
            result["attempts"][-1].update({
                "status": "failed",
                "error": str(e2),
                "traceback": traceback.format_exc()
            })
            
            result["status"] = "error"
            result["message"] = "Toutes les tentatives de connexion ont échoué"
    
    return result

@router.get("/connection-status", tags=["system"], summary="Vérifier l'état actuel de la connexion")
async def connection_status():
    """
    Retourne des informations sur l'état actuel de la connexion à la base de données,
    notamment les URLs utilisées et le moteur global.
    """
    from app.main import GLOBAL_ENGINE, WORKING_CONNECTION_URL
    from app.db.item_repo import SUCCESS_CONNECTION_URL, _engine
    import sys
    
    # Tenter une connexion simple pour vérifier
    connection_test = {"status": "pending"}
    try:
        from sqlalchemy import text
        if _engine:
            with _engine.connect() as conn:
                result = conn.execute(text("SELECT 1")).scalar()
                connection_test.update({
                    "status": "success",
                    "result": result
                })
        else:
            connection_test.update({
                "status": "not_initialized",
                "message": "Le moteur n'est pas encore initialisé"
            })
    except Exception as e:
        connection_test.update({
            "status": "error",
            "error": str(e)
        })
    
    return {
        "global_engine_exists": GLOBAL_ENGINE is not None,
        "item_repo_engine_exists": _engine is not None,
        "working_connection_url": WORKING_CONNECTION_URL.replace(
            "Ouibamba2025!", "********"
        ) if WORKING_CONNECTION_URL else None,
        "success_connection_url": SUCCESS_CONNECTION_URL.replace(
            "Ouibamba2025!", "********"
        ) if SUCCESS_CONNECTION_URL else None,
        "engines_same_instance": GLOBAL_ENGINE is _engine,
        "connection_test": connection_test,
        "python_id_global_engine": id(GLOBAL_ENGINE) if GLOBAL_ENGINE else None,
        "python_id_repo_engine": id(_engine) if _engine else None,
        "python_version": sys.version
    }

