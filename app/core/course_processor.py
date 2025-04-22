from typing import Dict, Any, Optional
from app.db.postgres import PostgresDataSource
from app.core.geocoding import GeocodingService
from app.core.utils import generate_route_hash, calculate_bird_distance, generate_address_hash
import logging
from geopy.distance import geodesic

logger = logging.getLogger(__name__)

class CourseProcessor:
    def __init__(self, ds: PostgresDataSource):
        self.ds = ds

    async def process_course(self, course_id: str):
        """Version optimisée qui recalcule uniquement les champs manquants"""
        try:
            # 1. Récupérer les données existantes
            existing_data = await self.ds.fetch_one("""
                SELECT 
                    c.hash_route,
                    cc.duree_trajet_min,
                    cc.points_passage_coords
                FROM course c
                LEFT JOIN coursecalcul cc ON c.hash_route = cc.hash_route
                WHERE c.course_id = %s
            """, (course_id,))

            # 2. Vérifier quels champs nécessitent un recalcul
            needs_recalc = {
                'hash_route': existing_data is None or not existing_data['hash_route'],
                'duree_trajet_min': existing_data is None or existing_data['duree_trajet_min'] is None,
                'points_passage_coords': existing_data is None or not existing_data['points_passage_coords']
            }

            if not any(needs_recalc.values()):
                logger.debug(f"Course {course_id} déjà complète - skip")
                return

            # 3. Récupérer les données brutes uniquement si nécessaire
            if any(needs_recalc.values()):
                raw_data = await self._get_raw_course_data(course_id)
                if not raw_data:
                    raise ValueError(f"Données introuvables pour la course {course_id}")

            # 4. Calculer uniquement les champs manquants
            updates = {}
            if needs_recalc['hash_route']:
                updates['hash_route'] = generate_route_hash(raw_data['lieu_prise_en_charge'], raw_data['destination'])
            
            if needs_recalc['duree_trajet_min']:
                updates['duree_trajet_min'] = geodesic(
                    (raw_data['pickup_lat'], raw_data['pickup_lng']),
                    (raw_data['dest_lat'], raw_data['dest_lng'])
                ).km * 2  # Exemple: 2 min/km

            if needs_recalc['points_passage_coords']:
                updates['points_passage_coords'] = await self._fetch_route_coordinates(raw_data)

            # 5. Mise à jour ciblée
            await self._update_missing_fields(course_id, updates)

        except Exception as e:
            logger.error(f"Échec course {course_id}: {str(e)}")
            raise

    async def _get_course_data(self, course_id: int) -> Optional[Dict[str, Any]]:
        """Récupère les données d'une course depuis la base"""
        query = """
            SELECT course_id, lieu_prise_en_charge, destination 
            FROM course WHERE course_id = %s
        """
        return await self.ds.fetch_one(query, (course_id,))

    async def _save_course_calcul(self, data: Dict[str, Any]) -> None:
        """Enregistre les calculs dans la table courseCalcul"""
        query = """
            INSERT INTO courseCalcul (
                hash_route, lieu_prise_en_charge, destination,
                lieu_prise_en_charge_lat, lieu_prise_en_charge_lng,
                destination_lat, destination_lng, distance_vol_oiseau_km,
                distance_routiere_km, duree_trajet_min, duree_trajet_secondes,
                points_passage, points_passage_coords
            ) VALUES (
                %(hash_route)s, %(lieu_prise_en_charge)s, %(destination)s,
                %(lieu_prise_en_charge_lat)s, %(lieu_prise_en_charge_lng)s,
                %(destination_lat)s, %(destination_lng)s, %(distance_vol_oiseau_km)s,
                %(distance_routiere)s, %(duree_trajet)s, %(duree_trajet_secondes)s,
                %(points_passage)s, %(points_passage_coords)s
            )
            ON CONFLICT (hash_route) DO UPDATE
            SET 
                distance_routiere_km = EXCLUDED.distance_routiere_km,
                duree_trajet_min = EXCLUDED.duree_trajet_min,
                duree_trajet_secondes = EXCLUDED.duree_trajet_secondes,
                points_passage = EXCLUDED.points_passage,
                points_passage_coords = EXCLUDED.points_passage_coords
        """
        await self.ds.execute_transaction(query, data)

    async def _update_course_route_hash(self, course_id: int, hash_route: str) -> None:
        """Met à jour le hash_route d'une course dans la base"""
        query = """
            UPDATE course
            SET hash_route = %s
            WHERE course_id = %s
        """
        await self.ds.execute_transaction(query, (hash_route, course_id))

    async def _get_raw_course_data(self, course_id: str) -> dict:
        """Récupère uniquement les données nécessaires aux calculs"""
        return await self.ds.fetch_one("""
            SELECT 
                lieu_prise_en_charge, destination,
                pickup_lat, pickup_lng, dest_lat, dest_lng
            FROM course_with_geodata  # Vue à créer si nécessaire
            WHERE course_id = %s
        """, (course_id,))

    async def _fetch_route_coordinates(self, data: dict) -> str:
        # Implementation of _fetch_route_coordinates method
        # This method should return a string representation of route coordinates
        # For example, it could return a JSON string of coordinates
        return "JSON_STRING_OF_COORDINATES"

    async def _update_missing_fields(self, course_id: str, updates: dict):
        """Met à jour uniquement les champs spécifiés"""
        if not updates:
            return

        # Construction dynamique de la requête
        set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
        values = list(updates.values())
        
        # Requête pour coursecalcul
        await self.ds.execute_transaction([
            (f"""
                INSERT INTO coursecalcul (hash_route, {', '.join(updates.keys())})
                VALUES (%s, {', '.join(['%s']*len(updates))})
                ON CONFLICT (hash_route) DO UPDATE SET
                    {set_clause}
            """, [updates.get('hash_route')] + values),
            
            # Mise à jour du hash_route dans course si nécessaire
            *([
                ("UPDATE course SET hash_route = %s WHERE course_id = %s", 
                 [updates['hash_route'], course_id])
            ] if 'hash_route' in updates else [])
        ])
