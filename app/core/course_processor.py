import hashlib
import json
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, Optional
import logging
from app.core.config import settings , get_settings , LIEUX_MAPPING_ADRESSE
import httpx
import pandas as pd
from app.core.utils import format_heure, save_and_upload_to_drive
import os

logger = logging.getLogger(__name__)

# Désactive complètement les logs de httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Désactive les logs DEBUG de la base de données
logging.getLogger("app.db.postgres").setLevel(logging.WARNING)

# Désactive les logs DEBUG de SQLAlchemy
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

class CourseProcessor:
    def __init__(self, ds):
        self.ds = ds
        self.logger = logging.getLogger(__name__)

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
                'distance_routiere_km': route_details['distance_meters'] / 1000,
                'duree_trajet_min': route_details['duration_seconds'] / 60,
                'duree_trajet_secondes': route_details['duration_seconds'],
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

    async def genererCourse(self, date_debut: str, date_fin: str, passed_year:int) -> pd.DataFrame:
        """
        Génère les courses en séparant le traitement des courses aller, retour et vers la salle.
        Prend en compte les erreurs pour ne pas générer de courses si des erreurs sont présentes.
        """
        try:
            self.logger.info("DEBUT genererCourse")

            # Récupérer les configurations
            settings = get_settings()
            JOUR_EVENEMENT = settings.JOUR_EVENEMENT
            ADRESSE_SALLE = settings.ADRESSE_SALLE.lower()
            PAYS_ORGANISATEUR = settings.PAYS_ORGANISATEUR.lower()

            # Définition des colonnes incluant les champs d'erreur
            columns = ["ID", "Prenom-Nom", "Telephone", "Nombre-prs-AR", "Provenance", 
                      "Arrivee-date", "Arrivee-vol", "Arrivee-heure", "Arrivee-Lieux",
                      "Hebergeur", "RESTAURATION", "Telephone-hebergeur", "Adresse-hebergement",
                      "Retour-date", "Nombre-prs-Ret", "Retour-vol", "Retour-heure",
                      "Retour-Lieux", "Destination", "vip", "transport_aller", "transport_retour",
                      "erreur_aller", "erreur_retour"]

            # Requêtes pour les courses aller - nombre de personnes en int retour a zero car pas besoin pour crer les courses aller
            query_aller = f"""
                SELECT "ID", "Prenom-Nom", "Telephone", cast(cast("Nombre-prs-AR" as float) as int) as "Nombre-prs-AR", "Provenance", 
                      "Arrivee-date", "Arrivee-vol", "Arrivee-heure", "Arrivee-Lieux",
                      "Hebergeur", "RESTAURATION", "Telephone-hebergeur", "Adresse-hebergement",
                      "Retour-date", 0 as "Nombre-prs-Ret", "Retour-vol",  "Retour-heure",
                      "Retour-Lieux", "Destination",   "vip" ,
                      "transport_aller", "transport_retour" ,
                      "erreur_aller" , "erreur_retour"
                FROM "Hotes" 
                WHERE evenement_annee = {passed_year}
                AND "ID" is not null
                AND ( "Prenom-Nom" is not null and "Prenom-Nom" != '' and "Prenom-Nom" != 'None' and "Prenom-Nom" != ' ')
                AND ( "Nombre-prs-AR" is not null and "Nombre-prs-AR" != '' and "Nombre-prs-AR" != 'None' and "Nombre-prs-AR" != ' ')
                AND ( "Arrivee-date" is not null  and "Arrivee-date" != '' and "Arrivee-date" != 'None' and "Arrivee-date" != ' ')
                AND ( "Arrivee-heure" is not null and "Arrivee-heure" != '' and "Arrivee-heure" != 'None' and "Arrivee-heure" != ' ')
                AND ( "Arrivee-Lieux" is not null  and "Arrivee-Lieux" != '' and "Arrivee-Lieux" != 'None' and "Arrivee-Lieux" != ' ' and lower("Arrivee-Lieux") != 'none')
                AND ( "Adresse-hebergement" is not null  and "Adresse-hebergement" != '' and "Adresse-hebergement" != 'None' and "Adresse-hebergement" != ' ' and lower("Adresse-hebergement") != 'none')
                AND ( "erreur_aller" is null OR "erreur_aller" = '' )
                
                AND lower(coalesce(transport_aller ,'oui' )) != 'non' ;
            """
            # Requêtes pour les courses retour 
            query_retour = f"""
                SELECT "ID", "Prenom-Nom", "Telephone", 0 as "Nombre-prs-AR", "Provenance", 
                      "Arrivee-date", "Arrivee-vol", "Arrivee-heure", "Arrivee-Lieux",
                      "Hebergeur", "RESTAURATION", "Telephone-hebergeur", "Adresse-hebergement",
                      "Retour-date", cast(cast("Nombre-prs-Ret" as float) as int) as "Nombre-prs-Ret", "Retour-vol", "Retour-heure",
                      "Retour-Lieux", "Destination",  "vip" , "transport_aller", "transport_retour" ,"erreur_aller" ,"erreur_retour"
                FROM "Hotes" 
                WHERE evenement_annee = {passed_year}
                AND "ID" is not null
                AND ( "Prenom-Nom" is not null and "Prenom-Nom" != '' and "Prenom-Nom" != 'None' and "Prenom-Nom" != ' ')
                AND "Retour-date" is not null and "Retour-date" != '' and "Retour-date" != 'None' and "Retour-date" != ' '         
                AND "Nombre-prs-Ret" is not null  and "Nombre-prs-Ret" != '' and "Nombre-prs-Ret" != 'None' and "Nombre-prs-Ret" != ' '
                AND "Retour-heure" is not null and "Retour-heure" != '' and "Retour-heure" != 'None' and "Retour-heure" != ' '
                AND "Retour-Lieux" is not null and "Retour-Lieux" != '' and "Retour-Lieux" != 'None' and "Retour-Lieux" != ' ' and lower("Retour-Lieux") != 'none'
                AND "Adresse-hebergement" is not null and "Adresse-hebergement" != '' and "Adresse-hebergement" != 'None' and "Adresse-hebergement" != ' ' and lower("Adresse-hebergement") != 'none'
                AND ("erreur_retour" is null OR "erreur_retour" = '')
                AND lower(coalesce(transport_retour ,'oui' )) != 'non' ;
            """

            # Exécution des requêtes
            hotes_aller = await self.ds.execute_query(query_aller)
            hotes_retour = await self.ds.execute_query(query_retour)

            # Conversion en DataFrames
            data_aller_df = pd.DataFrame(hotes_aller, columns=columns)
            data_retour_df = pd.DataFrame(hotes_retour, columns=columns)
            #data_df = pd.concat([data_aller_df, data_retour_df]).drop_duplicates(subset=['ID'])

            self.logger.info("Début transformation des données")
            # Nettoyage et préparation des données
            #data_df = self._prepare_dataframe(data_df)
            data_aller_df = self._prepare_dataframe(data_aller_df)
            data_retour_df = self._prepare_dataframe(data_retour_df)



            # Génération des courses
            courses = []
            
            # Traitement des courses aller
            courses.extend(self._generate_aller_courses(data_aller_df))
            
            # Traitement des courses retour
            courses.extend(self._generate_retour_courses(data_retour_df))
            
            # Traitement des courses vers la salle
            courses.extend(self._generate_salle_courses(data_aller_df))

            # Convertir en DataFrame
            courses_df = pd.DataFrame(courses)

            # Insertion dans la base de données
            await self._insert_courses(courses_df)
            
            FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
            if not FOLDER_ID:
                logger.error("GOOGLE_DRIVE_FOLDER_ID non trouvé dans le fichier .env")
                raise ValueError("GOOGLE_DRIVE_FOLDER_ID non trouvé dans le fichier .env")

            # Sauvegarde dans Google Drive
            await save_and_upload_to_drive(
                df=courses_df,
                folder_id=FOLDER_ID,
                file_prefix="courses",
                subfolder_name="courses",
                format_excel=True,
                index=False
            )

            self.logger.info("FIN genererCourse")
            return courses_df

        except Exception as e:
            self.logger.error(f"Erreur dans genererCourse : {e}")
            raise

    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prépare le DataFrame avec les transformations nécessaires"""
        df.columns = df.columns.str.strip()
        
        # Conversion et formatage des dates et heures
        for col in ['Arrivee-date', 'Retour-date']:
            df[col] = df[col].astype(str).fillna('')
            
        # Formatage des heures avec une regex plus robuste
        for col in ['Arrivee-heure', 'Retour-heure']:
            df[col] = df[col].fillna('').astype(str).apply(self._format_time)
        
        # Traitement des adresses
        settings = get_settings()
        PAYS_ORGANISATEUR = settings.PAYS_ORGANISATEUR.lower()
        
        LIEUX_MAPPING_ADRESSE_MINUSCULE = {k.lower(): v for k, v in LIEUX_MAPPING_ADRESSE.items()}
        
        # Traitement des lieux
        for col in ['Arrivee-Lieux', 'Retour-Lieux']:
            # Nettoyage des valeurs None et vides
            df[col] = df[col].replace(['None', 'none', 'NONE', ''], pd.NA)
            # Conversion en majuscules uniquement pour les valeurs non-NA
            df[col] = df[col].str.upper()
            # Création de la colonne _long avec mapping
            print(f"{col.lower()}_long")
            df[f"{col.lower()}_long"] = df[col].str.lower().replace(LIEUX_MAPPING_ADRESSE_MINUSCULE)
        
        # Traitement de l'adresse d'hébergement
        df['Adresse-hebergement'] = df['Adresse-hebergement'].replace(['None', 'none', 'NONE', ''], pd.NA)
        df['Adresse-hebergement'] = df['Adresse-hebergement'].str.lower().replace(LIEUX_MAPPING_ADRESSE_MINUSCULE)
        df['Adresse-hebergement'] = df['Adresse-hebergement'].apply(
            lambda x: f'{x}, {PAYS_ORGANISATEUR}' if pd.notna(x) and isinstance(x, str) and PAYS_ORGANISATEUR not in x else x
        )

        # Traitement des destinations pour les courses retour
        df['Retour-Lieux'] = df['Retour-Lieux'].replace(['None', 'none', 'NONE', ''], pd.NA)
        df['Retour-Lieux'] = df['Retour-Lieux'].str.lower().replace(LIEUX_MAPPING_ADRESSE_MINUSCULE)
        df['Retour-Lieux'] = df['Retour-Lieux'].apply(
            lambda x: f'{x}, {PAYS_ORGANISATEUR}' if pd.notna(x) and isinstance(x, str) and PAYS_ORGANISATEUR not in x else x
        )
            
        return df

    def _format_time(self, time_str: str) -> str:
        """Formate une chaîne de temps en format HH:MM standard"""
        import re
        
        # Nettoyage initial
        time_str = str(time_str).strip()
        if not time_str or time_str.lower() in ['nan', 'none', '']:
            return ''
            
        # Gestion spéciale pour le format "23h"
        if re.match(r'^\d{1,2}[hH]$', time_str):
            hours = int(time_str[:-1])
            if 0 <= hours <= 23:
                return f"{hours:02d}:00"
        
        # Normalisation des séparateurs
        time_str = time_str.replace(':-', ':').replace('h', ':').replace('H', ':')
        
        # Regex pour extraire les heures et minutes
        pattern = r'^(\d{1,2})(?::(\d{2})|h(\d{2})|H(\d{2})|)$'
        match = re.match(pattern, time_str)
        
        if match:
            hours = match.group(1)
            minutes = next((m for m in match.groups()[1:] if m is not None), '00')
            
            # Validation des valeurs
            hours = int(hours)
            minutes = int(minutes)
            
            if 0 <= hours <= 23 and 0 <= minutes <= 59:
                return f"{hours:02d}:{minutes:02d}"
        
        return ''

    def _generate_base_course(self, row, type_course: str) -> dict:
        """Génère un dictionnaire de base pour une course"""
        return {
            'prenom_nom': row['Prenom-Nom'],
            'telephone': row['Telephone'],
            'hebergeur': row.get('Hebergeur', None),
            'telephone_hebergement': row.get('Telephone-hebergeur', None),
            'hote_id': row['ID'],
            'vip': row.get('VIP', False),
            'type_course': type_course
        }

    def _generate_aller_courses(self, df: pd.DataFrame) -> list:
        """Génère les courses aller"""
        courses = []
        for _, row in df.iterrows():
            if pd.notnull(row['Arrivee-date']) and (pd.isnull(row['erreur_aller']) or row['erreur_aller'] == ''):
                course = self._generate_base_course(row, 'aller')
                course.update({
                    'nombre_personne': row['Nombre-prs-AR'],
                    'lieu_prise_en_charge_court': row['Arrivee-Lieux'],
                    'lieu_prise_en_charge': row['arrivee-lieux_long'] if pd.notna(row['arrivee-lieux_long']) else row['Arrivee-Lieux'],
                    'date_heure_prise_en_charge': pd.to_datetime(f"{row['Arrivee-date']} {row['Arrivee-heure']}"),
                    'num_vol': row.get('Arrivee-vol', None),
                    'destination_court': row['Adresse-hebergement'],
                    'destination': row['Adresse-hebergement'] # faux a verifier et mofif avant integrationrow['arrivee-lieux_long'] if pd.notna(row['arrivee-lieux_long']) else row['Arrivee-Lieux']
                })
                courses.append(course)
        return courses

    def _generate_retour_courses(self, df: pd.DataFrame) -> list:
        settings = get_settings()
        NOMBRE_MINUTES_AVANT_RETOUR = settings.NOMBRE_MINUTES_AVANT_RETOUR
        JOUR_FIN_EVENEMENT = settings.JOUR_FIN_EVENEMENT
        ADRESSE_SALLE = settings.ADRESSE_SALLE.lower()

        """Génère les courses retour"""
        courses = []
        for _, row in df.iterrows():
            if pd.notnull(row['Retour-date']) and (pd.isnull(row['erreur_retour']) or row['erreur_retour'] == ''):
                course = self._generate_base_course(row, 'retour')
                # Convertir la date de retour en datetime pour comparaison
                retour_date = pd.to_datetime(row['Retour-date']).strftime('%Y-%m-%d')
                if retour_date == JOUR_FIN_EVENEMENT:
                    course.update({
                        'nombre_personne': row['Nombre-prs-Ret'],
                        'lieu_prise_en_charge_court': ADRESSE_SALLE,
                        'lieu_prise_en_charge': ADRESSE_SALLE,
                        'date_heure_prise_en_charge': pd.to_datetime(f"{row['Retour-date']} {row['Retour-heure']}") - pd.Timedelta(minutes=NOMBRE_MINUTES_AVANT_RETOUR),
                        'num_vol': row.get('Retour-vol', None),
                        'destination_court': row['Retour-Lieux'],
                        'destination': row['retour-lieux_long'] if pd.notna(row['retour-lieux_long']) else row['Retour-Lieux']
                    })
                else:
                    course.update({
                        'nombre_personne': row['Nombre-prs-Ret'],
                        'lieu_prise_en_charge_court': row['Adresse-hebergement'],
                        'lieu_prise_en_charge': row['Adresse-hebergement'],
                        'date_heure_prise_en_charge': pd.to_datetime(f"{row['Retour-date']} {row['Retour-heure']}") - pd.Timedelta(minutes=NOMBRE_MINUTES_AVANT_RETOUR),
                        'num_vol': row.get('Retour-vol', None),
                        'destination_court': row['Retour-Lieux'],
                        'destination': row['retour-lieux_long'] if pd.notna(row['retour-lieux_long']) else row['Retour-Lieux']
                    })
                courses.append(course)
        return courses

    def _generate_salle_courses(self, df: pd.DataFrame) -> list:
        """Génère les courses vers la salle"""
        settings = get_settings()
        JOUR_EVENEMENT = settings.JOUR_EVENEMENT
        ADRESSE_SALLE = settings.ADRESSE_SALLE.lower()
        
        courses = []
        for _, row in df.iterrows():
            if pd.notnull(row['Arrivee-date']):
                arrivee_date = pd.to_datetime(row['Arrivee-date'])
                jour_evenement = pd.to_datetime(JOUR_EVENEMENT)
                
                if arrivee_date.date() < jour_evenement.date():
                    course = self._generate_base_course(row, 'vers_salle')
                    course.update({
                        'nombre_personne': row['Nombre-prs-AR'],
                        'lieu_prise_en_charge_court': row['Adresse-hebergement'],
                        'lieu_prise_en_charge': row['Adresse-hebergement'],
                        'date_heure_prise_en_charge': pd.to_datetime(
                            f"{JOUR_EVENEMENT} {settings.JOUR_EVENEMENT_HEURE_PRISE_EN_CHARGE}:{settings.JOUR_EVENEMENT_MINUTE_PRISE_EN_CHARGE}"
                        ),
                        'destination': ADRESSE_SALLE
                    })
                    courses.append(course)
        return courses

    async def _insert_courses(self, courses_df: pd.DataFrame):
        """Insère les courses dans la base de données"""
        for index, row in courses_df.iterrows():
            # Debug: Afficher les valeurs avant l'insertion
            print(f"\nTentative d'insertion pour l'index {index}:")
            print(f"prenom_nom: {row['prenom_nom']}")
            print(f"nombre_personne: {row['nombre_personne']} (type: {type(row['nombre_personne'])})")
            print(f"lieu_prise_en_charge: {row['lieu_prise_en_charge']}")
            print(f"destination: {row['destination']}")
            
            insert_query = """
                INSERT INTO course (
                    prenom_nom, telephone, nombre_personne,
                    lieu_prise_en_charge_court, lieu_prise_en_charge,
                    date_heure_prise_en_charge, num_vol,
                    destination_court, destination,
                    hebergeur, telephone_hebergement,
                    hote_id, vip, type_course
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (hote_id, date_heure_prise_en_charge) 
                DO UPDATE SET
                    prenom_nom = EXCLUDED.prenom_nom,
                    telephone = EXCLUDED.telephone,
                    nombre_personne = EXCLUDED.nombre_personne,
                    lieu_prise_en_charge_court = EXCLUDED.lieu_prise_en_charge_court,
                    lieu_prise_en_charge = EXCLUDED.lieu_prise_en_charge,
                    num_vol = EXCLUDED.num_vol,
                    destination_court = EXCLUDED.destination_court,
                    destination = EXCLUDED.destination,
                    hebergeur = EXCLUDED.hebergeur,
                    telephone_hebergement = EXCLUDED.telephone_hebergement,
                    vip = EXCLUDED.vip,
                    type_course = EXCLUDED.type_course
            """
            params = [
                row['prenom_nom'], row['telephone'], row['nombre_personne'],
                row['lieu_prise_en_charge_court'], row['lieu_prise_en_charge'],
                row['date_heure_prise_en_charge'], row.get('num_vol'),
                row.get('destination_court', ''), row['destination'],
                row.get('hebergeur'), row.get('telephone_hebergement'),
                row['hote_id'], row.get('vip', False),
                row.get('type_course', '')
            ]
            
            try:
                await self.ds.execute_transaction([(insert_query, params)])
            except Exception as e:
                print(f"\nERREUR lors de l'insertion pour l'index {index}:")
                print(f"Erreur: {str(e)}")
                print("Valeurs problématiques:")
                for i, param in enumerate(params):
                    print(f"Paramètre {i}: {param} (type: {type(param)})")
                raise

    def clean_time(self, time_str):
        """Nettoie les formats de temps comme '10:-40' ou '10h40'"""
        return (
            str(time_str)
            .replace(':-', ':')
            .replace('h', ':')
            .replace('H', ':')
        )