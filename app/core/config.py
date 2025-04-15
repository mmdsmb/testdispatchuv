import os
import socket
import subprocess
from typing import Any, Dict, Optional, List
from pydantic import PostgresDsn, validator
from pydantic_settings import BaseSettings

# Détecter l'environnement CI
IN_CI = os.environ.get("CI") == "true"
IN_DOCKER = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"

# DÉSACTIVATION COMPLÈTE IPV6
# Ajouter ces variables d'environnement pour forcer l'utilisation d'IPv4
os.environ["PGSSLMODE"] = "disable"
os.environ["DISABLE_IPV6"] = "1"

# Patcher directement la fonction socket.getaddrinfo pour ignorer IPv6
# Ce hook est plus direct que notre solution précédente
original_getaddrinfo = socket.getaddrinfo

def force_ipv4_getaddrinfo(*args, **kwargs):
    """Wrapper qui force socket.getaddrinfo à n'utiliser que IPv4."""
    # Forcer la famille d'adresses à IPv4
    args = list(args)
    if len(args) > 2:
        args[2] = socket.AF_INET  # Forcer IPv4
    else:
        kwargs['family'] = socket.AF_INET
    
    try:
        return original_getaddrinfo(*args, **kwargs)
    except Exception as e:
        print(f"Erreur dans getaddrinfo patché: {e}")
        # Si ça échoue, on essaie la version originale
        return original_getaddrinfo(*args, **kwargs)

# Remplacer la fonction socket.getaddrinfo par notre version
socket.getaddrinfo = force_ipv4_getaddrinfo

# Liste d'adresses IP connues pour Supabase (à mettre à jour si nécessaire)
SUPABASE_KNOWN_IPS = {
    "db.zpjemgpnfaeayofvnkzo.supabase.co": ["34.142.230.92"]
}

def resolve_hostname(hostname: str) -> List[str]:
    """
    Tente de résoudre un nom d'hôte en adresses IP de plusieurs façons.
    
    Args:
        hostname: Le nom d'hôte à résoudre
        
    Returns:
        Liste d'adresses IP (vide si aucune n'est trouvée)
    """
    ips = []
    
    # Si nous avons des IPs connues pour ce nom d'hôte, les utiliser
    if hostname in SUPABASE_KNOWN_IPS:
        print(f"Utilisation d'adresses IP connues pour {hostname}: {SUPABASE_KNOWN_IPS[hostname]}")
        return SUPABASE_KNOWN_IPS[hostname]
    
    # 1. Résolution standard
    try:
        print(f"Tentative de résolution standard de {hostname}")
        addr_info = socket.getaddrinfo(hostname, 5432, socket.AF_INET, socket.SOCK_STREAM)
        for info in addr_info:
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
        if ips:
            print(f"Résolution réussie pour {hostname}: {ips}")
            return ips
    except Exception as e:
        print(f"Échec de la résolution standard pour {hostname}: {e}")
    
    # 2. Tentative avec nslookup
    try:
        print(f"Tentative avec nslookup pour {hostname}")
        result = subprocess.run(["nslookup", hostname], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "Address:" in line and ":" in line:
                    ip = line.split(":")[-1].strip()
                    if ip not in ips and not ip.startswith("127."):
                        ips.append(ip)
            if ips:
                print(f"Résolution nslookup réussie pour {hostname}: {ips}")
                return ips
    except Exception as e:
        print(f"Échec de nslookup pour {hostname}: {e}")
    
    # 3. Tentative avec getent
    try:
        print(f"Tentative avec getent pour {hostname}")
        result = subprocess.run(["getent", "hosts", hostname], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if parts and parts[0] and not parts[0].startswith("127."):
                    ip = parts[0]
                    if ip not in ips:
                        ips.append(ip)
            if ips:
                print(f"Résolution getent réussie pour {hostname}: {ips}")
                return ips
    except Exception as e:
        print(f"Échec de getent pour {hostname}: {e}")
    
    print(f"Aucune méthode de résolution n'a fonctionné pour {hostname}")
    return ips

class Settings(BaseSettings):
    PROJECT_NAME: str = "FastAPI Project"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Supabase configuration
    SUPABASE_URL: str = "https://xqjvxqjvxqjvxqjvxqjv.supabase.co"
    SUPABASE_KEY: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhxanZ4cWp2eHFqdnF4cWp2eHFqdiIsInJvbGUiOiJhbm9uIiwiaWF0IjoxNzM5NjY5NjAwLCJleHAiOjIwNTUyNDU2MDB9.2QZQZQZQZQZQZQZQZQZQZQZQZQZQZQZQZQZQZQZQZQ"
    
    # Database configuration
    DB_HOST: str = "db.xqjvxqjvxqjvxqjvxqjv.supabase.co"
    DB_PORT: str = "5432"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "postgres"
    
    # Déclarer explicitement les champs qui causaient des erreurs
    POSTGRES_SERVER: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None
    SQLALCHEMY_DATABASE_URI: Optional[str] = None
    
    # Detect if we're in CI environment
    IN_CI: bool = os.getenv("CI", "false").lower() == "true"
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Permettre les champs supplémentaires

settings = Settings() 