from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict
from datetime import datetime, time
import pandas as pd
import gdown
import logging
from supabase import create_client, Client
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
from pathlib import Path
from app.core.config import get_settings
import base64
from tempfile import NamedTemporaryFile
from pydantic import field_validator
from app.db.postgres import PostgresDataSource
from pydantic_settings import BaseSettings


# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class ChauffeurBronze(BaseModel):
    horodateur: str = Field(..., alias="Horodateur")
    prenom_nom: str = Field(..., alias="Prénom et Nom")
    telephone: str = Field(..., alias="Numéro de téléphone (WhatsApp)")
    email: EmailStr = Field(..., alias="Email")
    type_chauffeur: str = Field(..., alias="Seriez-vous disponible en tant   ?")
    nombre_places: str = Field(..., alias="Nombre de places de votre voiture sans le chauffeur ?")
    disponible_22_debut: Optional[time] = Field(None, alias="Disponible le 22/05/2025 à partir de")
    disponible_22_fin: Optional[time] = Field(None, alias="Disponible le 22/05/2025 jusqu'à")
    disponible_23_debut: Optional[time] = Field(None, alias="Disponible le 23/05/2025 à partir de")
    disponible_23_fin: Optional[time] = Field(None, alias="Disponible le 23/05/2025 jusqu'à")
    disponible_24_debut: Optional[time] = Field(None, alias="Disponible le 24/05/2025 à partir de")
    disponible_24_fin: Optional[time] = Field(None, alias="Disponible le 24/05/2025 jusqu'à")
    disponible_25_debut: Optional[str] = Field(None, alias="Disponible le 25/05/2025 à partir de")
    disponible_25_fin: Optional[str] = Field(None, alias="Disponible le 25/05/2025 jusqu'à")
    code_postal: str = Field(..., alias="Votre code postal")
    carburant: Optional[str] = Field(None, alias="Carburant")
    commentaires: Optional[str] = Field(None, alias="Commentaires, remarques ou suggestions")
    evenement_annee: Optional[str] = None
    evenement_jour: Optional[str] = None
    actif: Optional[str] = Field(..., alias="actif")

    @field_validator('code_postal', mode='before')
    def code_postal_to_str(cls, v):
        return str(v) if v is not None else None

    @field_validator('horodateur', mode='before')
    def convert_datetime(cls, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    @field_validator('nombre_places', mode='before')
    def convert_int(cls, v):
        if isinstance(v, int):
            return str(v)
        return v

    @field_validator('disponible_22_debut', 'disponible_22_fin', 'disponible_23_debut', 'disponible_23_fin', 'disponible_24_debut', 'disponible_24_fin', 'disponible_25_debut', 'disponible_25_fin', mode='before')
    def convert_time(cls, v):
        if isinstance(v, time):
            return v.strftime("%H:%M")
        return v

    @field_validator('telephone', mode='before')
    def convert_telephone(cls, v):
        if isinstance(v, int):
            return str(v)
        return v

    class Config:
        allow_population_by_field_name = True
        

class ChauffeurBronzeSync:
    def __init__(self):
        self.supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
        self.drive_service = self._authenticate_drive()
        self.ds = PostgresDataSource()

    def _authenticate_drive(self):
        """Authentification avec le compte de service"""
        settings = get_settings()
        creds_base64 = settings.GOOGLE_CREDENTIALS_BASE64

        if not creds_base64:
            raise ValueError("La variable GOOGLE_CREDENTIALS_BASE64 n'est pas définie.")

        try:
            creds_json = base64.b64decode(creds_base64).decode("utf-8")
            with NamedTemporaryFile(suffix=".json", mode="w", delete=False) as temp_file:
                temp_file.write(creds_json)
                temp_file_path = temp_file.name

            creds = service_account.Credentials.from_service_account_file(temp_file_path)
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Erreur d'authentification : {e}")
            raise

    def download_from_drive(self, file_id: str, output_path: str = 'chauffeurs2025.xlsx') -> str:
        """Téléchargement d'un Google Sheet en format Excel (XLSX)"""
        try:
            # MIME type pour Excel
            request = self.drive_service.files().export_media(
                fileId=file_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            with open(output_path, 'wb') as f:
                f.write(request.execute())
            logger.info(f"Fichier Excel téléchargé : {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Erreur de téléchargement : {e}")
            raise

    def read_excel(self, file_path: str) -> List[ChauffeurBronze]:
        try:
            df = pd.read_excel(file_path)
            df = df.where(pd.notnull(df), None)
            
            # Filtrage des lignes invalides
            df = df[df["Email"].notnull()]
            
            chauffeurs = []
            for _, row in df.iterrows():
                try:
                    chauffeur = ChauffeurBronze(**row)
                    chauffeurs.append(chauffeur)
                except Exception as e:
                    logger.error(f"Erreur lors de la validation de la ligne : {row}")
                    logger.error(f"Erreur : {e}")
                    continue
                
            logger.info(f"Nombre de lignes valides lues : {len(chauffeurs)}")
            return chauffeurs
        except Exception as e:
            logger.error(f"Erreur de lecture du fichier Excel : {e}")
            raise

    async def get_existing_chauffeurs(self) -> Dict[str, Dict]:
        try:
            response = self.supabase.table('chauffeurbronze').select('*').execute()
            return {chauffeur['email']: chauffeur for chauffeur in response.data}
        except Exception as e:
            logger.error(f"Erreur de récupération : {e}")
            raise

    def compare_data(self, file_chauffeurs: List[ChauffeurBronze], existing_chauffeurs: Dict[str, Dict]) -> Dict:
        changes = {
            'to_insert': [],
            'to_update': [],
            'unchanged': []
        }

        for chauffeur in file_chauffeurs:
            chauffeur_dict = chauffeur.dict(by_alias=True)
            mapped_data = self.map_to_supabase_fields(chauffeur_dict)
            
            if not mapped_data:
                logger.error(f"Données invalides pour le chauffeur : {chauffeur_dict}")
                continue

            existing = existing_chauffeurs.get(mapped_data['email'])

            if not existing:
                changes['to_insert'].append(mapped_data)
            else:
                # Ne pas inclure les champs evenement dans les changements s'ils existent déjà
                changes_dict = {}
                for field, value in mapped_data.items():
                    if field in ['evenement_annee', 'evenement_jour'] and existing.get(field) is not None:
                        continue
                    if field != 'email' and existing.get(field) != value:
                        changes_dict[field] = value

                if changes_dict:
                    changes['to_update'].append({
                        'email': mapped_data['email'],
                        'changes': changes_dict,
                        'new_data': mapped_data
                    })
                else:
                    changes['unchanged'].append(mapped_data['email'])
        
        logger.info(f"Résultats de la comparaison : {len(changes['to_insert'])} insertions, "
                    f"{len(changes['to_update'])} mises à jour, "
                    f"{len(changes['unchanged'])} inchangés")
        return changes

    async def apply_changes(self, changes: Dict) -> Dict:
        try:
            if changes['to_insert']:
                logger.info(f"Préparation de l'insertion de {len(changes['to_insert'])} enregistrements")
                
                # Début de la transaction
                await self.ds.execute_query("BEGIN")
                
                for item in changes['to_insert']:
                    # Log des données avant insertion
                    logger.info(f"Données à insérer : {item}")
                    
                    # Validation des données requises
                    if not self.validate_data(item):
                        logger.error(f"Données invalides pour l'insertion : {item}")
                        continue
                    print(item['actif'])
                    # Construction de la requête UPSERT
                    query = """
                    INSERT INTO chauffeurbronze (
                        horodateur, prenom_nom, telephone, email, type_chauffeur,
                        nombre_places, code_postal, carburant, commentaires,
                        disponible_22_debut, disponible_22_fin,
                        disponible_23_debut, disponible_23_fin,
                        disponible_24_debut, disponible_24_fin,
                        disponible_25_debut, disponible_25_fin,
                        evenement_annee, evenement_jour,
                        actif
                    ) VALUES (
                        %(horodateur)s, %(prenom_nom)s, %(telephone)s, %(email)s, %(type_chauffeur)s,
                        %(nombre_places)s, %(code_postal)s, %(carburant)s, %(commentaires)s,
                        %(disponible_22_debut)s, %(disponible_22_fin)s,
                        %(disponible_23_debut)s, %(disponible_23_fin)s,
                        %(disponible_24_debut)s, %(disponible_24_fin)s,
                        %(disponible_25_debut)s, %(disponible_25_fin)s,
                        %(evenement_annee)s, %(evenement_jour)s,
                        %(actif)s
                    )
                    ON CONFLICT (email) DO UPDATE SET
                        horodateur = EXCLUDED.horodateur,
                        prenom_nom = EXCLUDED.prenom_nom,
                        telephone = EXCLUDED.telephone,
                        type_chauffeur = EXCLUDED.type_chauffeur,
                        nombre_places = EXCLUDED.nombre_places,
                        code_postal = EXCLUDED.code_postal,
                        carburant = EXCLUDED.carburant,
                        commentaires = EXCLUDED.commentaires,
                        disponible_22_debut = EXCLUDED.disponible_22_debut,
                        disponible_22_fin = EXCLUDED.disponible_22_fin,
                        disponible_23_debut = EXCLUDED.disponible_23_debut,
                        disponible_23_fin = EXCLUDED.disponible_23_fin,
                        disponible_24_debut = EXCLUDED.disponible_24_debut,
                        disponible_24_fin = EXCLUDED.disponible_24_fin,
                        disponible_25_debut = EXCLUDED.disponible_25_debut,
                        disponible_25_fin = EXCLUDED.disponible_25_fin,
                        evenement_annee = EXCLUDED.evenement_annee,
                        evenement_jour = EXCLUDED.evenement_jour,
                        actif = EXCLUDED.actif
                    RETURNING email
                    """
                    
                    try:
                        # Exécution de la requête
                        result = await self.ds.execute_query(query, item)
                        logger.info(f"Insertion réussie pour l'email : {item.get('email')}")
                    except Exception as e:
                        logger.error(f"Erreur lors de l'insertion pour l'email {item.get('email')} : {e}")
                        # Rollback en cas d'erreur
                        await self.ds.execute_query("ROLLBACK")
                        return {'success': False, 'error': str(e)}
                
                # Commit de la transaction
                await self.ds.execute_query("COMMIT")
                
                # Vérification finale
                count_query = "SELECT COUNT(*) FROM chauffeurbronze"
                count_result = await self.ds.execute_query(count_query)
                logger.info(f"Nombre total d'enregistrements dans la table : {count_result}")
                
                return {'success': True, 'upserted': len(changes['to_insert'])}
                
        except Exception as e:
            # Rollback en cas d'erreur
            await self.ds.execute_query("ROLLBACK")
            logger.error(f"Erreur upsert : {e}")
            return {'success': False, 'error': str(e)}

    async def sync(self, file_id: str, auto_apply: bool = False) -> Dict:
        try:
            # Récupérer la configuration
            settings = get_settings()
            jour_evenement = settings.JOUR_EVENEMENT
            
            # Extraire l'année et le jour de la date
            evenement_annee = jour_evenement.split('-')[0] if jour_evenement else None
            evenement_jour = jour_evenement if jour_evenement else None

            # Téléchargement du fichier
            file_path = self.download_from_drive(file_id)
            logger.info(f"Fichier téléchargé : {file_path}")

            # Lecture des données
            file_chauffeurs = self.read_excel(file_path)
            logger.info(f"Nombre de chauffeurs lus : {len(file_chauffeurs)}")

            # Ajouter les champs evenement_annee et evenement_jour à chaque chauffeur seulement s'ils sont null
            for chauffeur in file_chauffeurs:
                if chauffeur.evenement_annee is None:
                    chauffeur.evenement_annee = evenement_annee
                if chauffeur.evenement_jour is None:
                    chauffeur.evenement_jour = evenement_jour

            # Récupération des données existantes
            existing_chauffeurs = await self.get_existing_chauffeurs()
            logger.info(f"Nombre de chauffeurs existants : {len(existing_chauffeurs)}")

            # Comparaison et préparation des changements
            changes = self.compare_data(file_chauffeurs, existing_chauffeurs)
            logger.info(f"Changements à appliquer : {len(changes['to_insert'])} insertions")

            # Application des changements si auto_apply est True
            if auto_apply:
                result = await self.apply_changes(changes)
                return result

            return {"status": "Preview mode", "changes": changes}
        except Exception as e:
            logger.error(f"Erreur lors de la synchronisation : {e}")
            return {"success": False, "error": str(e)}

    def map_to_supabase_fields(self, chauffeur_dict: Dict) -> Dict:
        """
        Mappe les champs du fichier Excel vers les colonnes de la table Supabase.
        """
        try:
            mapped = {
                "horodateur": chauffeur_dict.get("Horodateur"),
                "prenom_nom": chauffeur_dict.get("Prénom et Nom"),
                "telephone": chauffeur_dict.get("Numéro de téléphone (WhatsApp)"),
                "email": chauffeur_dict.get("Email"),
                "type_chauffeur": chauffeur_dict.get("Seriez-vous disponible en tant   ?"),
                "nombre_places": chauffeur_dict.get("Nombre de places de votre voiture sans le chauffeur ?"),
                "disponible_22_debut": chauffeur_dict.get("Disponible le 22/05/2025 à partir de"),
                "disponible_22_fin": chauffeur_dict.get("Disponible le 22/05/2025 jusqu'à"),
                "disponible_23_debut": chauffeur_dict.get("Disponible le 23/05/2025 à partir de"),
                "disponible_23_fin": chauffeur_dict.get("Disponible le 23/05/2025 jusqu'à"),
                "disponible_24_debut": chauffeur_dict.get("Disponible le 24/05/2025 à partir de"),
                "disponible_24_fin": chauffeur_dict.get("Disponible le 24/05/2025 jusqu'à"),
                "disponible_25_debut": chauffeur_dict.get("Disponible le 25/05/2025 à partir de"),
                "disponible_25_fin": chauffeur_dict.get("Disponible le 25/05/2025 jusqu'à"),
                "code_postal": chauffeur_dict.get("Votre code postal"),
                "carburant": chauffeur_dict.get("Carburant"),
                "commentaires": chauffeur_dict.get("Commentaires, remarques ou suggestions"),
                "evenement_annee": chauffeur_dict.get("evenement_annee"),
                "evenement_jour": chauffeur_dict.get("evenement_jour"),
                "actif": chauffeur_dict.get("actif")
            }
            
            # Validation des champs obligatoires
            if not mapped["email"]:
                logger.error(f"Email manquant dans les données : {chauffeur_dict}")
                return None
            
            # Convertir les objets time en chaînes
            for key in mapped:
                if isinstance(mapped[key], time):
                    mapped[key] = mapped[key].strftime("%H:%M")
                
            return mapped
        except Exception as e:
            logger.error(f"Erreur lors du mapping des champs : {e}")
            return None

    def validate_data(self, data: Dict) -> bool:
        """
        Valide les données avant insertion.
        """
        required_fields = ["email", "prenom_nom", "telephone", "code_postal"]
        
        for field in required_fields:
            if not data.get(field):
                logger.error(f"Champ obligatoire manquant : {field}")
                return False
            
        return True
