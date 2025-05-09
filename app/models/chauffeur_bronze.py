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
        self.db = PostgresDataSource()

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
            # Convertir en dict et mapper les champs
            chauffeur_dict = chauffeur.dict(by_alias=True)
            mapped_data = self.map_to_supabase_fields(chauffeur_dict)
            
            if not mapped_data:
                logger.error(f"Données invalides pour le chauffeur : {chauffeur_dict}")
                continue

            existing = existing_chauffeurs.get(mapped_data['email'])

            if not existing:
                changes['to_insert'].append(mapped_data)
            else:
                if mapped_data != existing:
                    changes['to_update'].append({
                        'email': mapped_data['email'],
                        'changes': {
                            field: {'old': existing.get(field), 'new': value}
                            for field, value in mapped_data.items()
                            if field != 'email' and existing.get(field) != value
                        },
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
            # Récupérer les données à insérer
            validated_data = []
            for item in changes['to_insert']:
                if not item.get('email'):
                    logger.warning(f"Ligne ignorée : email manquant. Données : {item}")
                    continue
                validated_data.append(item)

            # Récupérer les données à mettre à jour (reconstituer la ligne complète)
            for update in changes['to_update']:
                # Vous devez avoir accès à la nouvelle version complète de la ligne
                # Si ce n'est pas le cas, il faut la retrouver dans le fichier Excel ou la stocker dans compare_data
                # Supposons que vous stockez la nouvelle version complète dans update['new_data']
                if 'new_data' in update and update['new_data'].get('email'):
                    validated_data.append(update['new_data'])
                else:
                    logger.warning(f"Ligne de mise à jour ignorée (incomplète) : {update}")

            if not validated_data:
                return {'success': False, 'error': 'Aucune donnée valide à insérer ou mettre à jour'}

            await self.db.connect()
            columns = list(validated_data[0].keys())
            placeholders = ', '.join(['%s'] * len(columns))
            query = f"""
            INSERT INTO chauffeurbronze ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT (email) DO UPDATE SET
                {', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col != 'email'])}
            """

            queries_with_params = []
            for data in validated_data:
                values = list(data.values())
                queries_with_params.append((query, values))

            try:
                await self.db.execute_transaction(queries_with_params)
                logger.info(f"{len(validated_data)} lignes insérées/mises à jour avec succès")
                return {'success': True, 'message': f"{len(validated_data)} lignes traitées"}
            except Exception as e:
                logger.error(f"Erreur lors de l'exécution de la transaction : {e}")
                return {'success': False, 'error': str(e)}

        except Exception as e:
            logger.error(f"Erreur dans apply_changes : {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await self.db.disconnect()

    async def sync(self, file_id: str, auto_apply: bool = False) -> Dict:
        try:
            # Téléchargement du fichier
            file_path = self.download_from_drive(file_id)
            logger.info(f"Fichier téléchargé : {file_path}")

            # Lecture des données
            file_chauffeurs = self.read_excel(file_path)
            logger.info(f"Nombre de chauffeurs lus : {len(file_chauffeurs)}")

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
                "commentaires": chauffeur_dict.get("Commentaires, remarques ou suggestions")
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
