import os
import socket
import subprocess
from typing import Any, Dict, Optional, List
from pydantic import PostgresDsn, validator
from pydantic_settings import BaseSettings
import logging
from pathlib import Path

# Détecter l'environnement CI
IN_CI = os.environ.get("CI") == "true"
IN_DOCKER = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"

# DÉSACTIVATION COMPLÈTE IPV6
# Ajouter ces variables d'environnement pour forcer l'utilisation d'IPv4
os.environ["PGSSLMODE"] = "disable"
os.environ["DISABLE_IPV6"] = "1"


# Liste d'adresses IP connues pour Supabase (à mettre à jour si nécessaire)
SUPABASE_KNOWN_IPS = {
    "db.zpjemgpnfaeayofvnkzo.supabase.co": ["34.142.230.92"]
}


class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Project"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Supabase Configuration
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # Database Configuration
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "postgres"
    
    # Environment
    IN_CI: bool = False
    
    # Nouveaux paramètres modulaires
    DB_ENGINE: str = os.getenv("DB_ENGINE", "postgres")  # postgres|mysql|etc
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    
    # Déclarer explicitement les champs qui causaient des erreurs
    POSTGRES_SERVER: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None
    SQLALCHEMY_DATABASE_URI: Optional[str] = None
    
    SUPABASE_POOLER_HOST: str
    SUPABASE_POOLER_PORT: int 
    SUPABASE_POOLER_DBNAME: str
    SUPABASE_POOLER_USER: str
    SUPABASE_POOLER_PASSWORD: str
    SUPABASE_POOLER_SSLMODE: str = "require"
    
    # Override database settings for CI environment
    if IN_CI:
        DB_HOST = "localhost"
        DB_PORT = "5432"
        DB_USER = "postgres"
        DB_PASSWORD = "postgres"
        DB_NAME = "test_db"
    
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        """Get the SQLAlchemy database URL."""
        if self.IN_CI:
            return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    GOOGLE_MAPS_API_URL: str = None  # Configuré via .env #"https://maps.googleapis.com/maps/api/geocode/json"
    GOOGLE_MAPS_API_KEY: str = None  # Configuré via .env
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Permettre les champs supplémentaires

settings = Settings() 

if os.environ.get('DISABLE_CONFIG_LOGGING'):
    # Désactive complètement la configuration des logs si DISABLE_CONFIG_LOGGING est défini
    pass
else:
    # Ancienne configuration (gardée pour compatibilité)
    LOG_DIR = Path(__file__).parent.parent / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_DIR / 'dispatch.log'),
            logging.StreamHandler()
        ]
    ) 