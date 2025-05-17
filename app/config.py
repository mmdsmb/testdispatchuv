from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Configuration de la base de données
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "dispatch"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"

    # Adresse de la salle
    ADRESSE_SALLE: str = "123 Rue de la Salle, 75000 Paris"

    # Configuration de l'API Google Maps
    GOOGLE_MAPS_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings() 