from typing import Optional, Tuple, Dict, Any
import httpx
from fastapi import HTTPException
from app.core.config import settings  # Importez votre configuration
import json
from math import radians, sin, cos, sqrt, atan2
import logging

logger = logging.getLogger(__name__)

class GeocodingService:
    @staticmethod
    async def get_coordinates(address: str, postal_code: str = None) -> Optional[Tuple[float, float]]:
        """Géocode une adresse ou un code postal."""
        if not address and not postal_code:
            logger.warning("Adresse et code postal manquants pour le géocodage")
            return None

        full_address = f"{address}, {postal_code}" if address and postal_code else (address or postal_code)
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={full_address}&key={settings.GOOGLE_MAPS_API_KEY}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

            if data["status"] == "OK":
                location = data["results"][0]["geometry"]["location"]
                return (location["lat"], location["lng"])
            else:
                logger.error(f"Échec du géocodage: {data.get('error_message', 'Unknown error')}")
                return None

        except Exception as e:
            logger.error(f"Erreur lors du géocodage: {str(e)}")
            return None

    @staticmethod
    async def get_route_details(origin: str, destination: str) -> Optional[Dict[str, Any]]:
        """Obtient les détails d'un trajet via l'API Directions de Google Maps"""
        DIRECTIONS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"
        params = {
            'origin': origin,
            'destination': destination,
            'key': settings.GOOGLE_MAPS_API_KEY
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(DIRECTIONS_API_URL, params=params)
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'OK':
                    route = data['routes'][0]['legs'][0]
                    waypoints = []
                    waypoints_coords = []

                    for step in route['steps']:
                        waypoints.append(step['html_instructions'])
                        start_loc = step['start_location']
                        end_loc = step['end_location']
                        waypoints_coords.append({
                            'start': {'lat': start_loc['lat'], 'lng': start_loc['lng']},
                            'end': {'lat': end_loc['lat'], 'lng': end_loc['lng']},
                            'instruction': step['html_instructions']
                        })

                    return {
                        'duration': route['duration']['text'],
                        'duration_seconds': route['duration']['value'],
                        'distance': route['distance']['text'],
                        'distance_meters': route['distance']['value'],
                        'waypoints': json.dumps(waypoints, ensure_ascii=False),
                        'waypoints_coords': json.dumps(waypoints_coords, ensure_ascii=False)
                    }
        return None

# Instance exportée pour une utilisation facile
geocoding_service = GeocodingService()
