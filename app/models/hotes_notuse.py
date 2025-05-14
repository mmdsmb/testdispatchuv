from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
import pandas as pd
import gdown
import logging
from supabase import create_client, Client
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import base64
from tempfile import NamedTemporaryFile
from app.core.config import get_settings
from app.db.postgres import PostgresDataSource

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Hotes(BaseModel):
    ID: int = Field(..., alias="ID")
    Prenom_Nom: str = Field(..., alias="Prenom-Nom")
    Telephone: str
    Nombre_prs_AR: str = Field(..., alias="Nombre-prs-AR")
    Provenance: str
    Arrivee_date: str = Field(..., alias="Arrivee-date")
    Arrivee_vol: Optional[str] = Field(None, alias="Arrivee-vol")
    Arrivee_heure: Optional[str] = Field(None, alias="Arrivee-heure")
    Arrivee_Lieux: Optional[str] = Field(None, alias="Arrivee-Lieux")
    Hebergeur: Optional[str] = None
    RESTAURATION: Optional[str] = None
    Telephone_hebergeur: Optional[str] = Field(None, alias="Telephone-hebergeur")
    Adresse_hebergement: Optional[str] = Field(None, alias="Adresse-hebergement")
    Retour_date: Optional[str] = Field(None, alias="Retour-date")
    Nombre_prs_Ret: Optional[str] = Field(None, alias="Nombre-prs-Ret")
    Retour_vol: Optional[str] = Field(None, alias="Retour-vol")
    Retour_heure: Optional[str] = Field(None, alias="Retour-heure")
    Retour_Lieux: Optional[str] = Field(None, alias="Retour-Lieux")
    Destination: Optional[str] = None
    Chauffeur: Optional[str] = None
    evenement_annee: Optional[str] = None
    evenement_jour: Optional[str] = None

    class Config:
        allow_population_by_field_name = True

class HotesSync:
    TABLE_NAME = 'Hotes'

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

    def download_from_drive(self, file_id: str, output_path: str = 'BD_MX-25.xlsx') -> str:
        """Téléchargement d'un Google Sheet en format Excel (XLSX)"""
        try:
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

    def read_excel(self, file_path: str) -> List[Hotes]:
        try:
            df = pd.read_excel(file_path)
            
            # Convert all NaN, NaT, and None values to None
            df = df.replace({pd.NaT: None, pd.NA: None})
            df = df.where(pd.notnull(df), None)
            
            # Filtrage des lignes invalides - correction de la condition booléenne
            df = df[df["ID"].notna()]
            
            hotes = []
            for _, row in df.iterrows():
                try:
                    # Convert row to dict and handle special values
                    row_dict = row.to_dict()
                    
                    # Special handling for VIP field
                    if "VIP" in row_dict:
                        vip_value = row_dict["VIP"]
                        if pd.isna(vip_value) or vip_value is None:
                            row_dict["VIP"] = "NON"
                        else:
                            vip_str = str(vip_value).strip().upper()
                            row_dict["VIP"] = "OUI" if vip_str in ["OUI", "YES", "Y", "1", "TRUE"] else "NON"
                    
                    # Handle other fields
                    for key, value in row_dict.items():
                        if key != "VIP":  # Skip VIP as it's already handled
                            if pd.isna(value) or value == 'nan' or value == 'NaT':
                                row_dict[key] = None
                            elif value is not None:
                                row_dict[key] = str(value)
                    
                    hote = Hotes(**row_dict)
                    hotes.append(hote)
                except Exception as e:
                    logger.error(f"Erreur lors de la validation de la ligne : {row}")
                    logger.error(f"Erreur : {e}")
                    continue
                
            logger.info(f"Nombre de lignes valides lues : {len(hotes)}")
            return hotes
        except Exception as e:
            logger.error(f"Erreur de lecture du fichier Excel : {e}")
            raise

    async def get_existing_hosts(self) -> Dict[int, Dict]:
        """Récupère les hôtes existants depuis Supabase"""
        try:
            response = self.supabase.table(self.TABLE_NAME).select('*').execute()
            return {host['ID']: host for host in response.data}
        except Exception as e:
            logger.error(f"Erreur de récupération : {e}")
            raise

    def compare_data(self, file_hosts: List[Hotes], existing_hosts: Dict[int, Dict]) -> Dict:
        changes = {
            'to_insert': [],
            'to_update': [],
            'unchanged': []
        }

        for host in file_hosts:
            host_dict = host.dict(by_alias=True)
            mapped_data = self.map_to_supabase_fields(host_dict)
            
            if not mapped_data:
                logger.error(f"Données invalides pour l'hôte : {host_dict}")
                continue

            existing = existing_hosts.get(mapped_data['ID'])

            if not existing:
                changes['to_insert'].append(mapped_data)
            else:
                changes_dict = {}
                for field, value in mapped_data.items():
                    if field in ['evenement_annee', 'evenement_jour'] and existing.get(field) is not None:
                        continue
                    if field != 'ID' and existing.get(field) != value:
                        changes_dict[field] = value

                if changes_dict:
                    changes['to_update'].append({
                        'id': mapped_data['ID'],
                        'changes': changes_dict,
                        'new_data': mapped_data
                    })
                else:
                    changes['unchanged'].append(mapped_data['ID'])
        
        logger.info(f"Résultats de la comparaison : {len(changes['to_insert'])} insertions, "
                    f"{len(changes['to_update'])} mises à jour, "
                    f"{len(changes['unchanged'])} inchangés")
        return changes

    async def apply_changes(self, changes: Dict) -> Dict:
        try:
            settings = get_settings()
            jour_evenement = settings.JOUR_EVENEMENT
            evenement_annee = jour_evenement.split('-')[0] if jour_evenement else None
            evenement_jour = jour_evenement if jour_evenement else None

            if changes['to_insert']:
                for host in changes['to_insert']:
                    if host.get('evenement_annee') is None:
                        host['evenement_annee'] = evenement_annee
                    if host.get('evenement_jour') is None:
                        host['evenement_jour'] = evenement_jour
                
                self.supabase.table(self.TABLE_NAME).insert(changes['to_insert']).execute()
                logger.info(f"{len(changes['to_insert'])} nouveaux hôtes insérés")

            for update in changes['to_update']:
                if update['changes'].get('evenement_annee') is None:
                    update['changes']['evenement_annee'] = evenement_annee
                if update['changes'].get('evenement_jour') is None:
                    update['changes']['evenement_jour'] = evenement_jour
                
                self.supabase.table(self.TABLE_NAME).update(update['changes']).eq('ID', update['id']).execute()
                logger.info(f"Mise à jour de l'hôte ID {update['id']}")

            return {'success': True, 'message': 'Changements appliqués avec succès'}
        except Exception as e:
            logger.error(f"Erreur dans apply_changes : {e}")
            return {'success': False, 'error': str(e)}

    def map_to_supabase_fields(self, host_dict: Dict) -> Dict:
        """Mappe les champs du fichier Excel vers les colonnes de la table Supabase"""
        try:
            # Map of Excel column names to Supabase column names
            field_mapping = {
                "ID": "ID",
                "Prenom-Nom": "Prenom-Nom",
                "Telephone": "Telephone",
                "VIP": "vip",
                "Nombre-prs-AR": "Nombre-prs-AR",
                "Provenance": "Provenance",
                "Arrivee-date": "Arrivee-date",
                "Arrivee-vol": "Arrivee-vol",
                "Arrivee-heure": "Arrivee-heure",
                "Arrivee-Lieux": "Arrivee-Lieux",
                "Transport_Aller": "transport_aller",
                "Hebergeur": "Hebergeur",
                "RESTAURATION": "RESTAURATION",
                "Telephone-hebergeur": "Telephone-hebergeur",
                "Adresse-hebergement": "Adresse-hebergement",
                "Retour-date": "Retour-date",
                "Nombre-prs-Ret": "Nombre-prs-Ret",
                "Retour-vol": "Retour-vol",
                "Retour-heure": "Retour-heure",
                "Retour-Lieux": "Retour-Lieux",
                "Destination": "Destination",
                "Transport_retour": "transport_retour",
                "Chauffeur": "Chauffeur"
            }
            
            mapped = {}
            for excel_field, value in host_dict.items():
                if excel_field in field_mapping:
                    mapped[field_mapping[excel_field]] = value
            
            if not self.validate_data(mapped):
                return None
                
            return mapped
        except Exception as e:
            logger.error(f"Erreur lors du mapping des champs : {e}")
            return None

    def validate_data(self, data: Dict) -> bool:
        """Valide les données avant insertion"""
        required_fields = ["ID", "Prenom-Nom", "Telephone", "Nombre-prs-AR", "Provenance", 
                         "Arrivee-date", "Arrivee-vol", "Arrivee-heure", "Arrivee-Lieux"]
        
        for field in required_fields:
            if not data.get(field):
                logger.error(f"Champ obligatoire manquant : {field}")
                return False
            
        return True

    async def sync(self, file_id: str = None, auto_apply: bool = False) -> Dict:
        try:
            settings = get_settings()
            jour_evenement = settings.JOUR_EVENEMENT
            
            evenement_annee = jour_evenement.split('-')[0] if jour_evenement else None
            evenement_jour = jour_evenement if jour_evenement else None

            if file_id is None:
                file_id = os.getenv('HOTES_FILE_ID')
                if not file_id:
                    raise ValueError("HOTES_FILE_ID non défini dans les variables d'environnement")

            file_path = self.download_from_drive(file_id)
            logger.info(f"Fichier téléchargé : {file_path}")

            file_hosts = self.read_excel(file_path)
            logger.info(f"Nombre d'hôtes lus : {len(file_hosts)}")

            for host in file_hosts:
                if host.evenement_annee is None:
                    host.evenement_annee = evenement_annee
                if host.evenement_jour is None:
                    host.evenement_jour = evenement_jour

            existing_hosts = await self.get_existing_hosts()
            logger.info(f"Nombre d'hôtes existants : {len(existing_hosts)}")

            changes = self.compare_data(file_hosts, existing_hosts)
            logger.info(f"Changements à appliquer : {len(changes['to_insert'])} insertions")

            if auto_apply:
                result = await self.apply_changes(changes)
                return result

            return {"status": "Preview mode", "changes": changes}
        except Exception as e:
            logger.error(f"Erreur lors de la synchronisation : {e}")
            return {"success": False, "error": str(e)}
