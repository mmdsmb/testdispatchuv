import os
import socket
import subprocess
from typing import Any, Dict, Optional, List
from pydantic import PostgresDsn, validator
from pydantic_settings import BaseSettings
import logging
from pathlib import Path
from functools import lru_cache
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
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "postgres")
    SQLALCHEMY_DATABASE_URI: Optional[str] = None
    
    SUPABASE_POOLER_HOST: str
    SUPABASE_POOLER_PORT: int 
    SUPABASE_POOLER_DBNAME: str
    SUPABASE_POOLER_USER: str
    SUPABASE_POOLER_PASSWORD: str
    SUPABASE_POOLER_SSLMODE: str = "require"
    
    # Configuration de l'API Google Maps
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")

    # Configuration de l'authentification de l'API de dispatch
    DISPATCH_API_USERNAME: str = os.getenv("DISPATCH_API_USERNAME", "admin")
    DISPATCH_API_PASSWORD: str = os.getenv("DISPATCH_API_PASSWORD", "admin")
    
    CHAUFFEURS_FILE_ID: str = os.getenv("CHAUFFEURS_FILE_ID", "")
    HOTES_FILE_ID: str = os.getenv("HOTES_FILE_ID", "")
    
    # Chemin du fichier de credentials Google Drive
    GOOGLE_DRIVE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_DRIVE_CREDENTIALS_PATH", "credentials/dispatchingchauffeur-481e58d1e194.json")
    GOOGLE_CREDENTIALS_BASE64: str = os.getenv("GOOGLE_CREDENTIALS_BASE64", "")
    
    HOTES_LOCAL_FILENAME: str = "BD_MX-25.xlsx"
        
    DUREE_GROUPE : int = 60  # coefficient d'ajustement ou Durée d'un groupe en minutes
    DESTINATION_DANS_GROUPAGE : str = "oui"  # oui/non ajouter Destination dans le groupage
    TIMEZONE : str = 'Europe/Paris'  # Fuseau horaire par défaut
    PAYS_ORGANISATEUR : str = "France"
    ADRESSE_SALLE : str = "2, Rue de la Falaise 95520 Osny, France"
    JOUR_EVENEMENT : str    = "2025-05-24"
    JOUR_EVENEMENT_HEURE_PRISE_EN_CHARGE : int  = 8 # heure de prise en charge des clients ou invités pour les amener à la salle (une valeur entre 0 et 23)
    JOUR_EVENEMENT_MINUTE_PRISE_EN_CHARGE : int = 30 # minutes de prise en charge des clients ou invités pour les amener à la salle (une valeur entre 0 et 59)
    # la combinaison de JOUR_EVENEMENT_HEURE_PRISE_EN_CHARGE et JOUR_EVENEMENT_MINUTE_PRISE_EN_CHARGE donne l'heure de prise en charge des clients ou invités pour les amener à la salle
    #"2024-05-10 08:30:00" si on a JOUR_EVENEMENT_HEURE_PRISE_EN_CHARGE = 8 et JOUR_EVENEMENT_MINUTE_PRISE_EN_CHARGE = 30
    JOUR_FIN_EVENEMENT : str = "2025-05-25"
    NOMBRE_MINUTES_AVANT_RETOUR : int = 180 #  pour calculer  la date_heure_prise_en_charge -180 minutes (3heures) par exemple avanr le depart du vol  
    #DUREE_ENTRE_MISSION_CHAUFFEUR : int   = 130 # delai de latence entre deux missions pour un chauffeur en minutes ou entre 2 prise en charge
    #GROUPE_PRIORITE_VANNE : int  = 12 # Pour les réaffectation SI >= 12 PRILIVIGIER VANNE + PETITE VOITURE . ENTRE 13 ET 16 2 VANNES -> Fixer
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
    
    GOOGLE_MAPS_API_URL: str = "https://maps.googleapis.com/maps/api/geocode/json"  # Default Google Maps API URL
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Permettre les champs supplémentaires

settings = Settings() 

if os.environ.get('DISABLE_CONFIG_LOGGING'):
    # Désactive complètement la configuration des logs si DISABLE_CONFIG_LOGGING est défini
    pass
else:
    # Configuration des logs
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
    

@lru_cache()
def get_settings() -> Settings:
    """Retourne les paramètres de configuration en cache."""
    return settings

# Mapping automatique des colonnes aux attributs pour les chauffeurs
CHAUFFEUR_COLUMNS_MAPPING = {
    "Horodateur": "horodateur",
    "Prénom et Nom": "prenom_nom", 
    "Numéro de téléphone (WhatsApp)": "telephone",
    "Email": "email",
    "Seriez-vous disponible en tant   ?": "type_chauffeur",
    "Nombre de places de votre voiture sans le chauffeur ?": "nombre_places",
    "Disponible le 22/05/2025 à partir de": "disponible_22_debut",
    "Disponible le 22/05/2025 jusqu'à": "disponible_22_fin",
    "Disponible le 23/05/2025 à partir de": "disponible_23_debut",
    "Disponible le 23/05/2025 jusqu'à": "disponible_23_fin",
    "Disponible le 24/05/2025 à partir de": "disponible_24_debut",
    "Disponible le 24/05/2025 jusqu'à": "disponible_24_fin",
    "Disponible le 25/05/2025 à partir de": "disponible_25_debut",
    "Disponible le 25/05/2025 jusqu'à": "disponible_25_fin",
    "Votre code postal": "code_postal",
    "Carburant": "carburant",
    "Commentaires, remarques ou suggestions": "commentaires",
    "evenement_annee": "evenement_annee",
    "evenement_jour": "evenement_jour"
}

# Mapping des disponibilités pour les chauffeurs
CHAUFFEUR_DISPONIBILITE_MAPPING = {
    "2025-05-22": {
        "debut": "disponible_22_debut",
        "fin": "disponible_22_fin"
    },
    "2025-05-23": {
        "debut": "disponible_23_debut",
        "fin": "disponible_23_fin"
    },
    "2025-05-24": {
        "debut": "disponible_24_debut",
        "fin": "disponible_24_fin"
    },
    "2025-05-25": {
        "debut": "disponible_25_debut",
        "fin": "disponible_25_fin"
    }
}

# Mapping des lieux spécifiques aux chauffeurs
CHAUFFEUR_LIEUX_MAPPING = {
    "DOMICILE": "Adresse du domicile",
    "GARE": "Gare la plus proche",
    "AEROPORT": "Aéroport le plus proche",
    "SALLE": settings.ADRESSE_SALLE,
    "AUTRE": "Autre lieu spécifié"
}

# Mapping automaique  des colonnes aux attributs pour les clients
    # ARRIVEE -> HEBERGEMENT
CLIENT_COLUMS_MAPPING_ARRIVEE = {
        "Prenom-Nom": "prenom_nom", 
        "Téléphone-voyageur": "telephone",
        "Nombre-prs-AR":"nombre_personne",
        "Arrivee-date": "date_prise_en_charge",
        "Arrivee-vol": "num_vol",
        "Arrivee-heure": "heure_prise_en_charge",
        "Arrivee-Lieux": "lieu_prise_en_charge",
        "arrivee_lieux_long": "lieu_prise_en_charge_long", # adresse plus longue ou plus détaillée pour la recuperation des coordonnées GPS
        "Provenance": "arrivee_provenance",
        "Hebergeur":"hebergeur",
        "Telephone-hebergeur":"telephone_hebergement",
        "Adresse-hebergement": "destination",
        "Arrivee-Transport": "transport",
        "Arrivee-Execution": "execution"
    } 

    #  HEBERGEMENT -> SALLE LE JOUR DU MAGAL 
CLIENT_COLUMS_MAPPING_SALLE = {
            "Prenom-Nom": "prenom_nom", 
            "Téléphone-voyageur": "telephone",
            "Nombre-prs-AR":"nombre_personne",
            "Hebergeur":"hebergeur",
            "Telephone-hebergeur":"telephone_hebergeur",
            "Adresse-hebergement": "lieu_prise_en_charge",
            "Arrivee-date": "date_prise_en_charge",
        } 

    #  SALLE -> RETOUR
CLIENT_COLUMS_MAPPING_RETOUR = {
            "Prenom-Nom": "prenom_nom", 
            "Téléphone-voyageur": "telephone",
            "Nombre-prs-Ret":"nombre_personne",
            "Retour-date": "retour_date", # date de depart du vol, du train,.... 
            "Retour-vol": "num_vol",
            "Retour-heure": "retour_heure", # heure de depart du vol, du train,.... voir  parametre general NOMBRE_MINUTES_AVANT_RETOUR pour calculer  la date_heure_prise_en_charge -180  minutes par exemple avan l'heure de retour
            "Retour-Lieux": "destination",
            "retour_lieux_long": "destination_long", #  adresse plus longue ou plus détaillée pour la recuperation des coordonnées GPS
            "Retour-Transport": "transport",
            "Retour-Execution": "execution"
        }


LIEUX_MAPPING_ADRESSE = {
    'CDG': 'Aéroport Paris-Charles de Gaulle, France',
    'ORLY': 'Aéroport Paris-Orly, France',
    'BEAUVAIS': 'Beauvais, France',
    'CDG': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T1': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T2': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T2A': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T2B': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T2C': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T2D': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T2E': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T2F': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T2G': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG T1': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG T2': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG T2A': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG T2B': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG T2C': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG T2D': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG T2E': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG T2F': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG T2G': 'Aéroport Paris-Charles de Gaulle, France',
    'ORLY-T1': 'Aéroport Paris-Orly, France',
    'ORLY-T2': 'Aéroport Paris-Orly, France',
    'ORLY T3': 'Aéroport Paris-Orly, France',
    'ORLY-T4': 'Aéroport Paris-Orly, France',
    'ORLY T1': 'Aéroport Paris-Orly, France',
    'ORLY T2': 'Aéroport Paris-Orly, France',
    'ORLY T3': 'Aéroport Paris-Orly, France',
    'ORLY T4': 'Aéroport Paris-Orly, France',
    'CDG 2': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG T2': 'Aéroport Paris-Charles de Gaulle, France',
    'ORLY T1': 'Aéroport Paris-Orly, France',
    'ORLY': 'Aéroport Paris-Orly, France',
    'CDG-T3': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T1': 'Aéroport Paris-Charles de Gaulle, France',
    'CDG-T': 'Aéroport Paris-Charles de Gaulle, France',
    'GARE DE LYON': 'Paris Gare de Lyon, France',
    'GARE DE BERCY': 'Gare de Bercy, Paris, France',
    'Paris la Défence Terminal Jules Verne': 'Paris la Défence Terminal Jules Verne, France',
    'PARIS LA DÉFENCE TERMINAL JULES VERNE': 'Paris la Défence Terminal Jules Verne, France',
    'Paris Massy': 'Paris Massy TGV, France',
    'PARIS MASSY': 'Paris Massy TGV, France',
    'Paris-Orly': 'Aéroport Paris-Orly, France',
    'Paris-Charles de Gaulle': 'Aéroport Paris-Charles de Gaulle, France',
    'GARE DE L\'EST': 'Gare de l\'Est, Paris, France',
    'Gare de l\'Est': 'Gare de l\'Est, Paris, France',
    'GARE DE LYON': 'GARE DE LYON, Paris, France',
    'Gare de Lyon': 'Gare de Lyon, Paris, France',
    'Salle': settings.ADRESSE_SALLE,
    'SALLE': settings.ADRESSE_SALLE,
    'DIRECT SALLE': settings.ADRESSE_SALLE,
    'DIRECTE A LA SALLE': settings.ADRESSE_SALLE,
    'DIRECTE À LA SALLE': settings.ADRESSE_SALLE,
    'DIRECT A LA SALLE': settings.ADRESSE_SALLE,
    'DIRECT À LA SALLE': settings.ADRESSE_SALLE,
    'À LA SALLE': settings.ADRESSE_SALLE,
    'A LA SALLE': settings.ADRESSE_SALLE,
    'directe a la salle': settings.ADRESSE_SALLE,
    'directe à la salle': settings.ADRESSE_SALLE,
    'direct a la salle': settings.ADRESSE_SALLE,
    'direct à la salle': settings.ADRESSE_SALLE,
    'à la salle': settings.ADRESSE_SALLE,
    'a la salle': settings.ADRESSE_SALLE

}