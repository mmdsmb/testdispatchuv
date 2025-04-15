import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlalchemy

from app.api.v1.api import api_router
from app.core.config import settings, SUPABASE_KNOWN_IPS
from app.db.item_repo import Base, get_engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Variable globale pour stocker le moteur et l'URL de connexion qui fonctionnent
# Cette variable sera utilisée par toutes les fonctions de l'application
GLOBAL_ENGINE = None
WORKING_CONNECTION_URL = None

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="A structured FastAPI project with versioning and Supabase integration",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Créer les tables au démarrage
@app.on_event("startup")
async def startup_event():
    global GLOBAL_ENGINE, WORKING_CONNECTION_URL
    
    logger.info("Initialisation de la base de données au démarrage...")
    
    # Définir explicitement sslmode=disable
    os.environ["PGSSLMODE"] = "disable"
    
    # Tenter plusieurs méthodes de connexion et utiliser celle qui fonctionne
    connection_methods = []
    
    # 1. Utiliser l'URL de l'engine SQLAlchemy standard
    connection_methods.append({
        "name": "standard_sqlalchemy",
        "url": settings.SQLALCHEMY_DATABASE_URL
    })
    
    # 2. Remplacer le nom d'hôte par l'IP directe
    ip = None
    if settings.DB_HOST in SUPABASE_KNOWN_IPS:
        ip = SUPABASE_KNOWN_IPS[settings.DB_HOST][0]
    else:
        # Essayer de résoudre l'IP
        try:
            import socket
            ip = socket.gethostbyname(settings.DB_HOST)
        except:
            ip = "34.142.230.92"  # IP de secours
        
    direct_ip_url = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{ip}:{settings.DB_PORT}/{settings.DB_NAME}"
    connection_methods.append({
        "name": "direct_ip",
        "url": direct_ip_url
    })
    
    # 3. Version simplifiée de l'URL avec l'IP
    simple_url = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{ip}:{settings.DB_PORT}/{settings.DB_NAME}"
    connection_methods.append({
        "name": "simple_url",
        "url": simple_url
    })
    
    # Tester chaque méthode de connexion
    success = False
    
    for method in connection_methods:
        try:
            logger.info(f"Tentative de connexion avec méthode: {method['name']}")
            
            # Options de connexion communes
            connect_args = {
                "connect_timeout": 30,
                "application_name": "FastAPI App",
                "sslmode": "disable"
            }
            
            # Créer un moteur temporaire pour tester
            engine = sqlalchemy.create_engine(
                method["url"],
                connect_args=connect_args,
                pool_pre_ping=True
            )
            
            # Tester la connexion
            with engine.connect() as conn:
                conn.execute(sqlalchemy.text("SELECT 1"))
            
            # Si on arrive ici, la connexion a réussi
            logger.info(f"Méthode {method['name']} a réussi!")
            GLOBAL_ENGINE = engine
            WORKING_CONNECTION_URL = method["url"]
            success = True
            break
            
        except Exception as e:
            logger.error(f"Méthode {method['name']} a échoué: {e}")
    
    # Si toutes les méthodes ont échoué, utiliser SQLite en mémoire
    if not success:
        logger.warning("Toutes les méthodes de connexion ont échoué!")
        logger.warning("Utilisation du moteur SQLite fallback: sqlite:///:memory:")
        
        # Créer un moteur SQLite en mémoire
        sqlite_url = "sqlite:///:memory:"
        GLOBAL_ENGINE = sqlalchemy.create_engine(sqlite_url)
        WORKING_CONNECTION_URL = sqlite_url
    
    # Créer les tables
    try:
        Base.metadata.create_all(bind=GLOBAL_ENGINE)
        logger.info("Tables créées avec succès")
    except Exception as e:
        logger.error(f"Erreur lors de la création des tables: {e}")

# Inclure les routes API
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Welcome to the FastAPI project with Supabase integration"} 