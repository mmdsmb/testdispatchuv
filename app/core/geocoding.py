from typing import Optional, Tuple, Dict, Any
import httpx
import logging
from math import radians, sin, cos, sqrt, atan2
from urllib.parse import quote, quote_plus
from importlib import reload
import app.core.config as config  # Nouvel import

# Rechargement correct du module
reload(config)
from app.core.config import settings

logging.basicConfig(level=logging.INFO, force=True)  # Niveau INFO
logger = logging.getLogger("httpx")
logger.setLevel(logging.WARNING)  # Désactive les logs de requêtes HTTP

# Supprimez les handlers existants (évite les doublons)
logger.handlers.clear()

# Ajoutez un handler console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logger.debug(f"Clé API après rechargement : {settings.GOOGLE_MAPS_API_KEY}")

class GeocodingService:
    @staticmethod
    async def get_coordinates(address: str, postal_code: str = None) -> Optional[Tuple[float, float]]:
        """
        Géocode une adresse ou un code postal via l'API Google Maps.
        
        Args:
            address: Adresse à géocoder.
            postal_code: Code postal optionnel pour affiner la recherche.
        
        Returns:
            Tuple (lat, lng) ou None si échec.
        """
        # Rechargement dynamique pour les tests (optionnel)
        try:
            reload(config)
            from app.core.config import settings
        except:
            pass

        if not address and not postal_code:
            logger.warning("Adresse et code postal manquants pour le géocodage")
            return None

        # Construction de l'adresse complète
        full_address = f"{address}, {postal_code}" if address and postal_code else (address or postal_code)
        params = {
            "address": quote(full_address),
            "key": settings.GOOGLE_MAPS_API_KEY,
            "region": "fr",
            "components": "country:fr"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params=params,
                    timeout=30.0
                )
                data = r.json()
                
                if data.get("status") != "OK":
                    logger.error(f"Échec API. Réponse : {data}")
                    return None
                    
                loc = data["results"][0]["geometry"]["location"]
                return (loc["lat"], loc["lng"])
                
        except Exception as e:
            logger.error(f"Erreur complète : {str(e)}")
            return None

    @staticmethod
    async def get_route_details(
        origin: str, 
        destination: str,
        mode: str = "driving"
    ) -> Optional[Dict[str, Any]]:
        """
        Obtient les détails d'un trajet via l'API Directions de Google Maps.
        
        Args:
            origin: Adresse de départ.
            destination: Adresse d'arrivée.
            mode: Mode de transport (driving, walking, bicycling, transit).
        
        Returns:
            Dictionnaire avec les détails du trajet ou None si échec.
        """
        url = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "key": settings.GOOGLE_MAPS_API_KEY
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if data["status"] != "OK":
                    logger.error(
                        f"Échec de l'API Directions. Status: {data['status']}, "
                        f"Erreur: {data.get('error_message', 'inconnue')}"
                    )
                    return None

                route = data["routes"][0]["legs"][0]
                waypoints_coords = [
                    {
                        "start": step["start_location"],
                        "end": step["end_location"],
                        "instruction": step["html_instructions"]
                    }
                    for step in route["steps"]
                ]

                return {
                    "duration": route["duration"]["text"],
                    "duration_seconds": route["duration"]["value"],
                    "distance": route["distance"]["text"],
                    "distance_meters": route["distance"]["value"],
                    "waypoints_coords": waypoints_coords,
                    "polyline": data["routes"][0].get("overview_polyline", {}).get("points")
                }

        except httpx.HTTPStatusError as e:
            logger.error(f"Erreur HTTP lors de la requête Directions: {e.response.status_code} - {str(e)}")
        except Exception as e:
            logger.error(f"Erreur inattendue lors de la requête Directions: {str(e)}")
        
        return None

# Instance exportée pour une utilisation facile
geocoding_service = GeocodingService()
