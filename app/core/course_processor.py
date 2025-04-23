import hashlib
import json
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, Optional
import logging
from app.core.config import settings
import httpx

logger = logging.getLogger(__name__)

class CourseProcessor:
    def __init__(self, ds):
        self.ds = ds
        #self.api_key = "AIzaSyAQWAj6hmmEkt45CFPWu1fQCi7b3_xxxxx"  # À remplacer par votre clé API
        self.api_key = settings.GOOGLE_MAPS_API_KEY
        
    def _generate_hash(self, text: str) -> str:
        """Génère un hash MD5 d'une chaîne de caractères"""
        return hashlib.md5(text.encode()).hexdigest()

    async def _get_geocode(self, address: str) -> Optional[Dict[str, float]]:
        """Obtient les coordonnées GPS d'une adresse (version asynchrone avec httpx)"""
        GOOGLE_MAPS_API_URL = "https://maps.googleapis.com/maps/api/geocode/json"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    GOOGLE_MAPS_API_URL,
                    params={"address": address, "key": self.api_key}
                )
                geodata = response.json()

                if geodata['status'] == 'OK':
                    location = geodata['results'][0]['geometry']['location']
                    return {
                        'lat': location['lat'],
                        'lng': location['lng']
                    }
                logger.error(f"Erreur de géocodage pour l'adresse {address}: {geodata['status']}")
                return None
        except Exception as e:
            logger.error(f"Erreur lors du géocodage: {str(e)}")
            return None

    def _calculate_distance(self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> float:
        """Calcule la distance à vol d'oiseau en km"""
        R = 6371  # Rayon de la Terre en km

        lat1, lon1, lat2, lon2 = map(radians, [origin_lat, origin_lng, dest_lat, dest_lng])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return round(R * c, 2)

    async def _get_route_details(self, origin: str, destination: str) -> Optional[Dict]:
        """Obtient les détails du trajet via Google Maps (version asynchrone avec httpx)"""
        DIRECTIONS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"

        try:
            params = {
                'origin': origin,
                'destination': destination,
                'key': self.api_key
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(DIRECTIONS_API_URL, params=params)
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
                logger.error(f"Erreur de calcul d'itinéraire: {data['status']}")
                return None
        except Exception as e:
            logger.error(f"Erreur lors du calcul d'itinéraire: {str(e)}")
            return None

    async def _save_course_calcul(self, course_data: Dict) -> None:
        """Sauvegarde les calculs dans la table courseCalcul"""
        query = """
            INSERT INTO courseCalcul (
                hash_route, lieu_prise_en_charge, destination,
                lieu_prise_en_charge_lat, lieu_prise_en_charge_lng,
                destination_lat, destination_lng,
                distance_vol_oiseau_km, distance_routiere_km,
                duree_trajet_min, duree_trajet_secondes,
                points_passage, points_passage_coords
            ) VALUES (
                %(hash_route)s, %(lieu_prise_en_charge)s, %(destination)s,
                %(lieu_prise_en_charge_lat)s, %(lieu_prise_en_charge_lng)s,
                %(destination_lat)s, %(destination_lng)s,
                %(distance_vol_oiseau_km)s, %(distance_routiere_km)s,
                %(duree_trajet_min)s, %(duree_trajet_secondes)s,
                %(points_passage)s, %(points_passage_coords)s
            ) ON CONFLICT (hash_route) DO UPDATE SET
                distance_routiere_km = EXCLUDED.distance_routiere_km,
                duree_trajet_min = EXCLUDED.duree_trajet_min,
                duree_trajet_secondes = EXCLUDED.duree_trajet_secondes,
                points_passage = EXCLUDED.points_passage,
                points_passage_coords = EXCLUDED.points_passage_coords
        """
        await self.ds.execute_transaction([(query, course_data)])

    async def _update_course_route_hash(self, course_id: int, hash_route: str) -> None:
        """Met à jour le hash_route dans la table course"""
        query = """
            UPDATE course 
            SET hash_route = %s
            WHERE course_id = %s
        """
        await self.ds.execute_transaction([(query, (hash_route, course_id))])

    async def process_course(self, course_id: int) -> None:
        """Traite une course et calcule ses informations"""
        try:
            # Récupérer les informations de la course
            course = await self.ds.fetch_one_dict("""
                SELECT course_id, lieu_prise_en_charge, destination
                FROM course 
                WHERE course_id = %s
            """, (course_id,))

            if not course:
                raise ValueError(f"Course {course_id} non trouvée")

            # Générer les hashs
            hash_prise_en_charge = self._generate_hash(course['lieu_prise_en_charge'])
            hash_destination = self._generate_hash(course['destination'])
            hash_route = f"{hash_prise_en_charge}_{hash_destination}"

            # Vérifier si les calculs existent déjà
            existing_calc = await self.ds.fetch_one_dict("""
                SELECT * FROM courseCalcul 
                WHERE hash_route = %s
            """, (hash_route,))

            if existing_calc and all([
                existing_calc['distance_routiere_km'],
                existing_calc['duree_trajet_min'],
                existing_calc['points_passage_coords']
            ]):
                logger.info(f"Calculs déjà existants pour la course {course_id}")
                await self._update_course_route_hash(course_id, hash_route)
                return

            # Obtenir les coordonnées (avec await)
            pickup_coords = await self._get_geocode(course['lieu_prise_en_charge'])
            dest_coords = await self._get_geocode(course['destination'])

            if not pickup_coords or not dest_coords:
                raise ValueError("Impossible d'obtenir les coordonnées GPS")

            # Calculer la distance à vol d'oiseau
            distance_vol_oiseau = self._calculate_distance(
                pickup_coords['lat'], pickup_coords['lng'],
                dest_coords['lat'], dest_coords['lng']
            )

            # Obtenir les détails du trajet (avec await)
            route_details = await self._get_route_details(
                course['lieu_prise_en_charge'],
                course['destination']
            )

            if not route_details:
                raise ValueError("Impossible d'obtenir les détails du trajet")

            # Préparer les données pour l'insertion
            course_data = {
                'hash_route': hash_route,
                'lieu_prise_en_charge': course['lieu_prise_en_charge'],
                'destination': course['destination'],
                'lieu_prise_en_charge_lat': pickup_coords['lat'],
                'lieu_prise_en_charge_lng': pickup_coords['lng'],
                'destination_lat': dest_coords['lat'],
                'destination_lng': dest_coords['lng'],
                'distance_vol_oiseau_km': distance_vol_oiseau,
                'distance_routiere_km': float(route_details['distance_meters']) / 1000,
                'duree_trajet_min': int(route_details['duration_seconds']) // 60,
                'duree_trajet_secondes': int(route_details['duration_seconds']),
                'points_passage': route_details['waypoints'],
                'points_passage_coords': route_details['waypoints_coords']
            }

            # Sauvegarder les calculs
            await self._save_course_calcul(course_data)
            
            # Mettre à jour le hash_route dans la course
            await self._update_course_route_hash(course_id, hash_route)
            
            logger.info(f"Course {course_id} traitée avec succès")

        except Exception as e:
            logger.error(f"Erreur lors du traitement de la course {course_id}: {str(e)}")
            raise