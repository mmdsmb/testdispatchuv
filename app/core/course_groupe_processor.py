import hashlib
import json
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, Optional
import logging
from app.core.config import settings
import httpx
from app.core.routeAnalyzer import RouteAnalyzer
import pandas as pd
from datetime import datetime, timedelta
import pandas as pd
from app.core.utils import save_and_upload_to_drive
import hashlib
import os
logger = logging.getLogger(__name__)

# Désactive complètement les logs de httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Désactive les logs DEBUG de la base de données
logging.getLogger("app.db.postgres").setLevel(logging.WARNING)

# Désactive les logs DEBUG de SQLAlchemy
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

class CourseGroupeProcessor:
    def __init__(self, ds):
        self.ds = ds
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

    async def _update_course_groupe_route_hash(self, groupe_id: int, hash_route: str) -> None:
        """Met à jour le hash_route dans la table courseGroupe"""
        query = """
            UPDATE courseGroupe 
            SET hash_route = %s
            WHERE groupe_id = %s
        """
        await self.ds.execute_transaction([(query, (hash_route, groupe_id))])

    async def process_course_groupe(self, groupe_id: int) -> None:
        """Traite un groupe de courses et calcule ses informations"""
        try:
            # Récupérer les informations du groupe
            groupe = await self.ds.fetch_one_dict("""
                SELECT groupe_id, lieu_prise_en_charge, destination
                FROM courseGroupe 
                WHERE groupe_id = %s
            """, (groupe_id,))

            if not groupe:
                raise ValueError(f"Groupe {groupe_id} non trouvé")

            # Récupération des coordonnées
            pickup_coords = await self._get_geocode(groupe['lieu_prise_en_charge'])
            dest_coords = await self._get_geocode(groupe['destination'])

            if not pickup_coords or not dest_coords:
                raise ValueError("Impossible d'obtenir les coordonnées GPS")

            # Génération des hash
            hash_prise_en_charge = self._generate_hash(groupe['lieu_prise_en_charge'])
            hash_destination = self._generate_hash(groupe['destination'])

            # Sauvegarde dans adresseGps
            await self.ds.execute_transaction([(
                """
                INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (hash_address) DO UPDATE
                SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                """,
                (hash_prise_en_charge, groupe['lieu_prise_en_charge'], pickup_coords['lat'], pickup_coords['lng'])
            )])

            await self.ds.execute_transaction([(
                """
                INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (hash_address) DO UPDATE
                SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                """,
                (hash_destination, groupe['destination'], dest_coords['lat'], dest_coords['lng'])
            )])

            # Calculer la distance à vol d'oiseau
            distance_vol_oiseau = self._calculate_distance(
                pickup_coords['lat'], pickup_coords['lng'],
                dest_coords['lat'], dest_coords['lng']
            )

            # Obtenir les détails du trajet
            route_details = await self._get_route_details(
                groupe['lieu_prise_en_charge'],
                groupe['destination']
            )

            if not route_details:
                raise ValueError("Impossible d'obtenir les détails du trajet")

            # Préparer les données pour l'insertion
            course_data = {
                'hash_route': f"{hash_prise_en_charge}_{hash_destination}",
                'lieu_prise_en_charge': groupe['lieu_prise_en_charge'],
                'destination': groupe['destination'],
                'lieu_prise_en_charge_lat': pickup_coords['lat'],
                'lieu_prise_en_charge_lng': pickup_coords['lng'],
                'destination_lat': dest_coords['lat'],
                'destination_lng': dest_coords['lng'],
                'distance_vol_oiseau_km': distance_vol_oiseau,
                'distance_routiere_km': route_details['distance_meters'] / 1000,
                'duree_trajet_min': route_details['duration_seconds'] / 60,
                'duree_trajet_secondes': route_details['duration_seconds'],
                'points_passage': route_details['waypoints'],
                'points_passage_coords': route_details['waypoints_coords']
            }

            # Sauvegarder les calculs
            await self._save_course_calcul(course_data)
            
            # Mettre à jour le hash_route dans le groupe
            await self._update_course_groupe_route_hash(groupe_id, course_data['hash_route'])
            
            logger.info(f"Groupe {groupe_id} traité avec succès")

        except Exception as e:
            logger.error(f"Erreur lors du traitement du groupe {groupe_id}: {str(e)}")
            raise 

    async def group_courses(
        self, 
        mode_groupage: str = "simple",
        similarite_percent: int = 80,
        window_minutes: int = 30,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        reset_groups: bool = False,
        export_to_drive: bool = True
    ) -> None:
        """
        Groupe les courses selon le mode spécifié
        
        Args:
            export_to_drive (bool): Si True, exporte les groupes vers Google Drive
            mode_groupage (str): "simple" ou "similarite"
            similarite_percent (int): Pourcentage de similarité (1-100) pour le mode "similarite"
            window_minutes (int): Fenêtre temporelle en minutes pour le groupage
            start_date (str): Date de début au format 'yyyy-MM-dd HH:mm:ss'
            end_date (str): Date de fin au format 'yyyy-MM-dd HH:mm:ss'
            reset_groups (bool): Si True, supprime les groupes existants dans la période
        """
        try:
            # Conversion des dates en objets datetime
            start_dt = datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S') if start_date else None
            end_dt = datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S') if end_date else None

            # Suppression des groupes existants si reset_groups=True
            if reset_groups and start_dt and end_dt:
                await self._reset_existing_groups(start_dt, end_dt)

            # Récupérer les données enrichies avec filtre de date
            df_data_enrichi = await self._get_enriched_data(start_dt, end_dt, reset_groups)
            
            if df_data_enrichi.empty:
                logger.info("Aucune donnée enrichie trouvée")
                return

            # Séparer les VIP et non-VIP
            df_vip = df_data_enrichi[df_data_enrichi['vip'] == True]
            df_non_vip = df_data_enrichi[df_data_enrichi['vip'] == False]

            if mode_groupage == "simple":
                await self._groupage_simple(df_vip, df_non_vip, window_minutes)
            else:
                await self._groupage_similarite(df_vip, df_non_vip, similarite_percent, window_minutes)

            # Traitement des groupes
            await self._process_groups()

            # Export vers Google Drive si demandé
            if export_to_drive:
                await self._export_groups_to_drive(start_dt, end_dt)

        except Exception as e:
            logger.error(f"Erreur dans group_courses: {str(e)}")
            raise

    async def _reset_existing_groups(self, start_date: datetime, end_date: datetime) -> None:
        """Supprime les groupes existants dans la période et réinitialise les courses"""
        # 1. Récupérer les groupes à supprimer
        groupes = await self.ds.fetch_all("""
            SELECT groupe_id 
            FROM courseGroupe 
            WHERE date_heure_prise_en_charge BETWEEN %s AND %s
        """, (start_date, end_date))
        
        # 2. Supprimer les groupes
        if groupes:
            # Vérifier le type de résultat (dict ou tuple)
            sample_row = groupes[0]
            if hasattr(sample_row, '_fields'):  # Cas des named tuples
                groupe_ids = [groupe.groupe_id for groupe in groupes]
            elif isinstance(sample_row, dict):  # Cas des dictionnaires
                groupe_ids = [groupe['groupe_id'] for groupe in groupes]
            else:  # Cas des tuples simples
                groupe_ids = [groupe[0] for groupe in groupes]
            
            await self.ds.execute_transaction([(
                "DELETE FROM courseGroupe WHERE groupe_id = %s",
                (groupe_id,)
            ) for groupe_id in groupe_ids])
        
        # 3. Réinitialiser les groupe_id des courses
        await self.ds.execute_transaction([(
            "UPDATE course SET groupe_id = NULL WHERE date_heure_prise_en_charge BETWEEN %s AND %s",
            (start_date, end_date)
        )])

    async def _ensure_address_coordinates(self, address: str, hash_address: str) -> None:
        """Vérifie et complète les coordonnées manquantes"""
        # Vérifier et générer le hash si nécessaire
        if not hash_address:
            hash_address = self._generate_hash(address)
            logger.warning(f"Hash manquant généré pour l'adresse: {address}")

        # Vérifier si l'adresse existe déjà
        existing = await self.ds.fetch_one("""
            SELECT latitude, longitude 
            FROM adresseGps 
            WHERE hash_address = %s
        """, (hash_address,))
        
        if not existing or None in existing:
            # Si coordonnées manquantes, géocoder
            coords = await self._get_geocode(address)
            if coords:
                await self.ds.execute_transaction([(
                    """
                    INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (hash_address) DO UPDATE
                    SET latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude
                    """,
                    (hash_address, address, coords['lat'], coords['lng'])
                )])
                return hash_address  # Retourner le hash utilisé
            else:
                logger.error(f"Échec du géocodage pour l'adresse: {address}")
                return None
        return hash_address

    async def _get_enriched_data(
        self, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        reset_groups: bool = False
    ) -> pd.DataFrame:
        """Récupère les données enrichies avec vérification des coordonnées"""
        base_query = """
            SELECT 
                c.*,
                c.lieu_prise_en_charge_court,
                c.destination_court,
                cc.distance_vol_oiseau_km,
                cc.distance_routiere_km,
                cc.duree_trajet_min,
                cc.duree_trajet_secondes,
                cc.points_passage,
                cc.points_passage_coords,
                ag1.latitude as lieu_prise_en_charge_lat,
                ag1.longitude as lieu_prise_en_charge_lng,
                ag2.latitude as destination_lat,
                ag2.longitude as destination_lng
            FROM course c
            LEFT JOIN coursecalcul cc ON c.hash_route = cc.hash_route
            LEFT JOIN adresseGps ag1 ON c.hash_lieu_prise_en_charge = ag1.hash_address
            LEFT JOIN adresseGps ag2 ON c.hash_destination = ag2.hash_address
        """
        
        where_clauses = []
        params = []
        
        # Filtre de date
        if start_date and end_date:
            where_clauses.append("c.date_heure_prise_en_charge BETWEEN %s AND %s")
            params.extend([start_date, end_date])
        
        # Filtre groupe_id si reset_groups=False
        if not reset_groups:
            where_clauses.append("c.groupe_id IS NULL")
        
        # Construction de la requête
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
        
        base_query += " ORDER BY c.date_heure_prise_en_charge"
        
        try:
            rows = await self.ds.fetch_all(base_query, params)
            df = pd.DataFrame(rows) if rows else pd.DataFrame()

            # Compléter les coordonnées manquantes
            if not df.empty:
                # Parcourir toutes les lignes pour vérifier les adresses
                for _, row in df.iterrows():
                    # Pour le lieu de prise en charge
                    if pd.isna(row['lieu_prise_en_charge_lat']) or pd.isna(row['lieu_prise_en_charge_lng']):
                        new_hash = await self._ensure_address_coordinates(
                            row['lieu_prise_en_charge'],
                            row['hash_lieu_prise_en_charge']
                        )
                        if new_hash and not row['hash_lieu_prise_en_charge']:
                            # Mettre à jour le hash dans la course si on l'a généré
                            await self.ds.execute_transaction([(
                                "UPDATE course SET hash_lieu_prise_en_charge = %s WHERE course_id = %s",
                                (new_hash, row['course_id'])
                            )])
                    
                    # Pour la destination
                    if pd.isna(row['destination_lat']) or pd.isna(row['destination_lng']):
                        new_hash = await self._ensure_address_coordinates(
                            row['destination'],
                            row['hash_destination']
                        )
                        if new_hash and not row['hash_destination']:
                            # Mettre à jour le hash dans la course si on l'a généré
                            await self.ds.execute_transaction([(
                                "UPDATE course SET hash_destination = %s WHERE course_id = %s",
                                (new_hash, row['course_id'])
                            )])

                # Recharger les données mises à jour
                updated_rows = await self.ds.fetch_all(base_query, params)
                return pd.DataFrame(updated_rows) if updated_rows else pd.DataFrame()
            
            return df
        
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des données enrichies: {str(e)}")
            raise

    async def _process_groups(self) -> None:
        """Traite tous les groupes nécessitant des calculs"""
        groupes = await self.ds.fetch_all("""
            SELECT groupe_id 
            FROM courseGroupe 
            WHERE hash_route IS NULL OR hash_route = ''
        """)
        
        for groupe in groupes:
            try:
                await self.process_course_groupe(groupe[0])
            except Exception as e:
                logger.error(f"Erreur groupe {groupe[0]}: {str(e)}")
                continue

    async def _groupage_simple(self, df_vip: pd.DataFrame, df_non_vip: pd.DataFrame, window_minutes: int) -> None:
        """Groupage simple basé sur les critères existants"""
        # Traiter les VIP individuellement
        for _, row in df_vip.iterrows():
            await self._create_groupe(row, is_vip=True)

        # Grouper les non-VIP
        for _, row in df_non_vip.iterrows():
            window_start = row['date_heure_prise_en_charge'] - timedelta(minutes=window_minutes)
            window_end = row['date_heure_prise_en_charge'] + timedelta(minutes=window_minutes)
            
            # Vérifier si un groupe compatible existe
            existing_group = await self.ds.fetch_one("""
                SELECT groupe_id 
                FROM courseGroupe 
                WHERE date_heure_prise_en_charge BETWEEN %s AND %s
                AND lieu_prise_en_charge = %s 
                AND destination = %s
                AND vip = false
                LIMIT 1
            """, (window_start, window_end, row['lieu_prise_en_charge'], row['destination']))
            
            if existing_group and existing_group[0]:  # Vérifier si le tuple n'est pas vide et contient un groupe_id
                await self._update_groupe(existing_group[0], row)  # Accéder au premier élément du tuple
            else:
                await self._create_groupe(row, is_vip=False)

    async def _groupage_similarite(self, df_vip: pd.DataFrame, df_non_vip: pd.DataFrame, similarite_percent: int, window_minutes: int) -> None:
        """Groupage basé sur la similarité des trajets"""
        # Traiter les VIP individuellement
        for _, row in df_vip.iterrows():
            await self._create_groupe(row, is_vip=True)

        if df_non_vip.empty:
            return

        analyzer = RouteAnalyzer(
            time_window_minutes=window_minutes,
            similarity_threshold=similarite_percent/10000,
            num_points=3,
            clustering_eps=similarite_percent/10000
        )

        df_grouped = analyzer.analyze_routes(
            df_non_vip,
            datetime_column='date_heure_prise_en_charge',
            output_file=None
        )

        for group_id in df_grouped['groupe_similaire'].unique():
            if group_id >= 0:
                group_rows = df_grouped[df_grouped['groupe_similaire'] == group_id]
                first_row = group_rows.iloc[0]
                
                # Collecter les adresses distinctes
                lieux_prise = group_rows['lieu_prise_en_charge'].unique().tolist()
                destinations = group_rows['destination'].unique().tolist()
                
                # Trouver la destination la plus éloignée
                max_distance = 0
                destination_eloignee = None
                origine_lat = first_row['lieu_prise_en_charge_lat']
                origine_lng = first_row['lieu_prise_en_charge_lng']
                
                for dest in destinations:
                    dest_row = group_rows[group_rows['destination'] == dest].iloc[0]
                    dest_lat = dest_row['destination_lat']
                    dest_lng = dest_row['destination_lng']
                    distance = self._calculate_distance(origine_lat, origine_lng, dest_lat, dest_lng)
                    if distance > max_distance:
                        max_distance = distance
                        destination_eloignee = {
                            'address': dest,
                            'lat': dest_lat,
                            'lng': dest_lng,
                            'distance_km': distance
                        }

                # Créer le groupe avec les nouvelles données
                groupe_id = await self._create_groupe(
                    first_row, 
                    is_vip=False,
                    lieux_prise=lieux_prise,
                    destinations=destinations,
                    destination_eloignee=destination_eloignee
                )
                
                for _, row in group_rows.iloc[1:].iterrows():
                    await self._update_groupe(groupe_id, row)

    async def _create_groupe(
        self, 
        row: pd.Series, 
        is_vip: bool,
        lieux_prise: list = None,
        destinations: list = None,
        destination_eloignee: dict = None
    ) -> int:
        """Crée un nouveau groupe de courses avec les données étendues"""
        query = """
            INSERT INTO courseGroupe (
                date_heure_prise_en_charge, nombre_personne, vip,
                lieu_prise_en_charge, destination,
                lieu_prise_en_charge_court, destination_court,
                lieu_prise_en_charge_json, destination_json,
                date_heure_prise_en_charge_json,
                hash_lieu_prise_en_charge, hash_destination,
                date_time_window, hash_route
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING groupe_id
        """
        
        # Préparation des données JSON
        lieu_prise_json = json.dumps({
            'liste': lieux_prise or [row['lieu_prise_en_charge']],
            'coordonnees': {
                'lat': row['lieu_prise_en_charge_lat'],
                'lng': row['lieu_prise_en_charge_lng']
            }
        }, ensure_ascii=False)
        
        destination_json = json.dumps({
            'liste': destinations or [row['destination']],
            'plus_eloignee': destination_eloignee or {
                'address': row['destination'],
                'lat': row['destination_lat'],
                'lng': row['destination_lng'],
                'distance_km': row['distance_vol_oiseau_km']
            }
        }, ensure_ascii=False)

        params = (
            row['date_heure_prise_en_charge'],
            row['nombre_personne'],
            is_vip,
            row['lieu_prise_en_charge'],
            row['destination'],
            row.get('lieu_prise_en_charge_court', ''),
            row.get('destination_court', ''),
            lieu_prise_json,
            destination_json,
            json.dumps({'window': row['date_heure_prise_en_charge'].isoformat()}),
            row['hash_lieu_prise_en_charge'],
            row['hash_destination'],
            row['date_heure_prise_en_charge'],
            row['hash_route']
        )
        
        result = await self.ds.execute_transaction([(query, params)])
        groupe_id = result[0][0]
        await self._update_course_group(row['course_id'], groupe_id)
        return groupe_id

    async def _update_groupe(self, groupe_id: int, row: pd.Series) -> None:
        """Met à jour un groupe existant avec une nouvelle course"""
        # Mettre à jour la course avec le groupe_id
        await self._update_course_group(row['course_id'], groupe_id)
        
        # Mettre à jour le nombre de personnes dans le groupe
        await self.ds.execute_transaction([("""
            UPDATE courseGroupe 
            SET nombre_personne = nombre_personne + %s
            WHERE groupe_id = %s
        """, (row['nombre_personne'], groupe_id))])

    async def _update_course_group(self, course_id: int, groupe_id: int) -> None:
        """Met à jour le groupe_id d'une course"""
        await self.ds.execute_transaction([("""
            UPDATE course 
            SET groupe_id = %s
            WHERE course_id = %s
        """, (groupe_id, course_id))])

    async def _export_groups_to_drive(self, start_date: datetime, end_date: datetime) -> None:
        """Exporte les groupes de courses vers Google Drive sous forme Excel"""
        try:
            # Récupérer les données des groupes
            query = """
                SELECT * FROM courseGroupe
                WHERE date_heure_prise_en_charge BETWEEN %s AND %s
                ORDER BY date_heure_prise_en_charge
            """
            groupes = await self.ds.fetch_all(query, (start_date, end_date))
            
            if not groupes:
                logger.info("Aucun groupe à exporter")
                return

            # Convertir en DataFrame
            df_groupes = pd.DataFrame(groupes)
            
            # Supprimer les fuseaux horaires des colonnes datetime
            datetime_cols = df_groupes.select_dtypes(include=['datetime64[ns, UTC]']).columns
            for col in datetime_cols:
                df_groupes[col] = df_groupes[col].dt.tz_localize(None)
            
            # Configurer l'export
            FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
            if not FOLDER_ID:
                logger.error("GOOGLE_DRIVE_FOLDER_ID non trouvé dans le fichier .env")
                raise ValueError("Configuration Google Drive manquante")

            # Nom du fichier avec la période
            date_str = start_date.strftime('%Y-%m-%d')
            if start_date.date() != end_date.date():
                date_str += f"_{end_date.strftime('%Y-%m-%d')}"
            
            # Sauvegarde dans Google Drive
            await save_and_upload_to_drive(
                df=df_groupes,
                folder_id=FOLDER_ID,
                file_prefix=f"groupes_courses_{date_str}",
                subfolder_name="groupes_courses",
                format_excel=True,
                index=False
            )
            
            logger.info(f"Export des groupes terminé ({len(df_groupes)} groupes)")

        except Exception as e:
            logger.error(f"Erreur lors de l'export des groupes: {str(e)}")
            raise 