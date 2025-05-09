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
            return [ChauffeurBronze(**row) for _, row in df.iterrows()]
        except Exception as e:
            logger.error(f"Erreur de lecture : {e}")
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
            chauffeur_dict = self.map_to_supabase_fields(chauffeur.dict(by_alias=True))
            existing = existing_chauffeurs.get(chauffeur.email)

            if not existing:
                changes['to_insert'].append(chauffeur_dict)
            else:
                if chauffeur_dict != existing:
                    changes['to_update'].append({
                        'email': chauffeur.email,
                        'changes': {
                            field: {'old': existing.get(field), 'new': value}
                            for field, value in chauffeur_dict.items()
                            if field != 'email' and existing.get(field) != value
                        }
                    })
                else:
                    changes['unchanged'].append(chauffeur.email)
        
        # logger.info(f"Résultats de la comparaison : {changes}")  # À commenter
        return changes

    async def apply_changes(self, changes: Dict) -> Dict:
        try:
            if changes['to_insert']:
                validated_data = []
                for item in changes['to_insert']:
                    mapped_data = self.map_to_supabase_fields(item)
                    validated_data.append(mapped_data)

                await self.db.connect()
                
                if validated_data:
                    columns = list(validated_data[0].keys())
                    placeholders = ', '.join(['%s'] * len(columns))
                    query = f"""
                    INSERT INTO chauffeurbronze ({', '.join(columns)})
                    VALUES ({placeholders})
                    ON CONFLICT (email) DO UPDATE SET
                        {', '.join([f'"{col}" = EXCLUDED."{col}"' for col in columns if col != 'email'])}
                    """
                    
                    logger.info(f"Nombre de lignes à insérer : {len(validated_data)}")
                    logger.debug(f"Requête générée : {query}")

                    # Exécuter chaque ligne dans une transaction
                    for data in validated_data:
                        values = list(data.values())
                        await self.db.execute_query(query, values)

                return {'success': True}
        except Exception as e:
            logger.error(f"Erreur upsert : {e}")
            return {'success': False, 'error': str(e)}
        finally:
            await self.db.disconnect()

    async def sync(self, file_id: str, auto_apply: bool = False) -> Dict:
        try:
            # (1) Téléchargement
            file_path = self.download_from_drive(file_id)
            logger.info(f"Fichier téléchargé avec succès : {file_path}")

            # (2) Lecture Excel
            file_chauffeurs = self.read_excel(file_path)
            #logger.info(f"Nombre de lignes lues : {len(file_chauffeurs)} | Exemple : {file_chauffeurs[0].dict() if file_chauffeurs else 'Aucune donnée'}")

            # (3) Récupération des données existantes
            existing_chauffeurs = await self.get_existing_chauffeurs()
            logger.info(f"Nombre d'entrées existantes : {len(existing_chauffeurs)}")

            # (4) Comparaison
            changes = self.compare_data(file_chauffeurs, existing_chauffeurs)
            #logger.info(f"Résultats de la comparaison : {changes}")

            # (5) Application
            if auto_apply:
                result = await self.apply_changes(changes)
                #logger.info(f"Résultat de l'application : {result}")
                return result

            return {"status": "Preview mode", "changes": changes}
        except Exception as e:
            logger.error(f"ERREUR GLOBALE : {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

    def map_to_supabase_fields(self, chauffeur_dict: Dict) -> Dict:
        return {
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
