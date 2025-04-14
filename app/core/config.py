import os
from typing import Any, Dict, Optional
from pydantic import PostgresDsn, validator
from pydantic_settings import BaseSettings

# Détecter l'environnement CI
IN_CI = os.environ.get("CI") == "true"

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Project"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database settings - valeurs par défaut pour l'environnement CI
    POSTGRES_SERVER: str = "localhost" if IN_CI else ""
    POSTGRES_USER: str = "test" if IN_CI else ""
    POSTGRES_PASSWORD: str = "test" if IN_CI else ""
    POSTGRES_DB: str = "test_db" if IN_CI else ""
    SQLALCHEMY_DATABASE_URI: Optional[PostgresDsn] = None

    @validator("SQLALCHEMY_DATABASE_URI", pre=True)
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        
        # Si nous sommes en CI, utiliser psycopg2 qui est mieux supporté dans l'environnement CI
        scheme = "postgresql" if IN_CI else "postgresql+psycopg"
        
        # Pour le CI, on reconstruit manuellement la chaîne de connexion
        if IN_CI:
            # Format manuel pour éviter les problèmes de chemin
            return f"{scheme}://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}@{values.get('POSTGRES_SERVER')}/{values.get('POSTGRES_DB')}"
        
        # Pour développement, on utilise le builder original
        return PostgresDsn.build(
            scheme=scheme,
            username=values.get("POSTGRES_USER"),
            password=values.get("POSTGRES_PASSWORD"),
            host=values.get("POSTGRES_SERVER"),
            path=f"/{values.get('POSTGRES_DB') or ''}",
        )

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings() 