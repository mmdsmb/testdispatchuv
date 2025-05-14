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
    Arrivee_vol: str = Field(..., alias="Arrivee-vol")
    Arrivee_heure: str = Field(..., alias="Arrivee-heure")
    Arrivee_Lieux: str = Field(..., alias="Arrivee-Lieux")
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
    vip: Optional[str] = Field(None, alias="VIP")  # Changé de "VIP" à "vip"
    transport_aller: Optional[str] = Field(None, alias="Transport_Aller")  # Correction ici
    transport_retour: Optional[str] = Field(None, alias="Transport_retour")  # Correction ici
    evenement_annee: Optional[str] = None
    evenement_jour: Optional[str] = None

    class Config:
        allow_population_by_field_name = True

class HotesSync:
    TABLE_NAME = 'Hotes'  # Sans les guillemets

    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv('SUPABASE_URL'),
            os.getenv('SUPABASE_KEY')
        )
        self.drive_service = self._authenticate_drive()

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

    def read_excel(self, file_path: str) -> List[Hotes]:
        try:
            df = pd.read_excel(file_path)
            df = df.where(pd.notnull(df), None)
            
            # Convertir les valeurs NaN en None
            df = df.replace({pd.NA: None})
            
            # Renommer les colonnes pour correspondre aux alias du modèle
            column_mapping = {
                'Prenom_Nom': 'Prenom-Nom',
                'Nombre_prs_AR': 'Nombre-prs-AR',
                'Arrivee_date': 'Arrivee-date',
                'Arrivee_vol': 'Arrivee-vol',
                'Arrivee_heure': 'Arrivee-heure',
                'Arrivee_Lieux': 'Arrivee-Lieux',
                'Telephone_hebergeur': 'Telephone-hebergeur',
                'Adresse_hebergement': 'Adresse-hebergement',
                'Retour_date': 'Retour-date',
                'Nombre_prs_Ret': 'Nombre-prs-Ret',
                'Retour_vol': 'Retour-vol',
                'Retour_heure': 'Retour-heure',
                'Retour_Lieux': 'Retour-Lieux',
                'transport_aller': 'transport_aller',  # Correction ici
                'transport_retour': 'transport_retour'  # Correction ici
            }
            
            # Renommer les colonnes
            df = df.rename(columns=column_mapping)
            
            # Gérer spécifiquement la colonne VIP
            if 'VIP' in df.columns:
                df['vip'] = df['VIP']  # Créer une nouvelle colonne 'vip' à partir de 'VIP'
                df = df.drop('VIP', axis=1)  # Supprimer l'ancienne colonne 'VIP'
            
            # Convertir les valeurs en chaînes de caractères
            for col in df.columns:
                df[col] = df[col].astype(str).replace('nan', None)
            
            logger.info("Colonnes après traitement:")
            logger.info(df.columns.tolist())
            logger.info("Exemples de valeurs VIP:")
            if 'vip' in df.columns:
                logger.info(df[['ID', 'vip']].head())
            
            hotes = []
            for _, row in df.iterrows():
                try:
                    # Convertir le dictionnaire en respectant les alias
                    hote_dict = {k: v for k, v in row.items() if v is not None}
                    hote = Hotes(**hote_dict)
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
        """Compare les données et identifie les différences"""
        changes = {
            'to_insert': [],
            'to_update': [],
            'unchanged': []
        }

        for host in file_hosts:
            host_dict = host.dict(by_alias=True)
            existing = existing_hosts.get(host.ID)

            if not existing:
                changes['to_insert'].append(host_dict)
            else:
                # Ne pas inclure les champs evenement dans les changements s'ils existent déjà
                changes_dict = {}
                for field, value in host_dict.items():
                    if field in ['evenement_annee', 'evenement_jour'] and existing.get(field) is not None:
                        continue
                    if field != 'ID' and existing.get(field) != value:
                        changes_dict[field] = value

                if changes_dict:
                    changes['to_update'].append({
                        'id': host.ID,
                        'changes': changes_dict
                    })
                else:
                    changes['unchanged'].append(host.ID)
        
        logger.info(f"Changements détectés : {len(changes['to_insert'])} insertions, {len(changes['to_update'])} mises à jour")
        return changes

    async def apply_changes(self, changes: Dict) -> Dict:
        """Applique les changements dans Supabase"""
        try:
            # Récupérer la configuration
            settings = get_settings()
            jour_evenement = settings.JOUR_EVENEMENT
            evenement_annee = jour_evenement.split('-')[0] if jour_evenement else None
            evenement_jour = jour_evenement if jour_evenement else None

            if changes['to_insert']:
                # Ajouter les champs evenement aux insertions seulement s'ils sont null
                for hote in changes['to_insert']:
                    if hote.get('evenement_annee') is None:
                        hote['evenement_annee'] = evenement_annee
                    if hote.get('evenement_jour') is None:
                        hote['evenement_jour'] = evenement_jour
                
                self.supabase.table(self.TABLE_NAME).insert(changes['to_insert']).execute()
                logger.info(f"{len(changes['to_insert'])} nouveaux hôtes insérés")

            for update in changes['to_update']:
                # Ne pas forcer la mise à jour des champs evenement s'ils existent déjà
                if update['changes'].get('evenement_annee') is None:
                    update['changes']['evenement_annee'] = evenement_annee
                if update['changes'].get('evenement_jour') is None:
                    update['changes']['evenement_jour'] = evenement_jour
                
                self.supabase.table(self.TABLE_NAME).update(update['changes']).eq('ID', update['id']).execute()
                logger.info(f"Mise à jour de l'hôte ID {update['id']}")

            return {'success': True, 'message': 'Changements appliqués avec succès'}
        except Exception as e:
            logger.error(f"Erreur lors de l'application des changements : {e}")
            return {'success': False, 'error': str(e)}

    async def sync(self, file_id: str = None, auto_apply: bool = False) -> Dict:
        try:
            # Récupérer la configuration
            settings = get_settings()
            jour_evenement = settings.JOUR_EVENEMENT  # Assurez-vous que cette variable existe dans votre config
            
            # Extraire l'année et le jour de la date
            evenement_annee = jour_evenement.split('-')[0] if jour_evenement else None
            evenement_jour = jour_evenement if jour_evenement else None

            # Si file_id n'est pas fourni, utiliser celui de l'environnement
            if file_id is None:
                file_id = os.getenv('HOTES_FILE_ID')
                if not file_id:
                    raise ValueError("HOTES_FILE_ID non défini dans les variables d'environnement")

            # Téléchargement du fichier
            file_path = self.download_from_drive(file_id)
            logger.info(f"Fichier téléchargé : {file_path}")

            # Lecture des données
            file_hotes = self.read_excel(file_path)
            logger.info(f"Nombre d'hôtes lus : {len(file_hotes)}")

            # Ajouter les champs evenement_annee et evenement_jour seulement s'ils sont null
            for hote in file_hotes:
                if hote.evenement_annee is None:
                    hote.evenement_annee = evenement_annee
                if hote.evenement_jour is None:
                    hote.evenement_jour = evenement_jour

            # Récupération des données existantes
            existing_hotes = await self.get_existing_hosts()
            logger.info(f"Nombre d'hôtes existants : {len(existing_hotes)}")

            # Comparaison et préparation des changements
            changes = self.compare_data(file_hotes, existing_hotes)
            logger.info(f"Changements à appliquer : {len(changes['to_insert'])} insertions")

            # Application des changements si auto_apply est True
            if auto_apply:
                result = await self.apply_changes(changes)
                return result

            return {"status": "Preview mode", "changes": changes}
        except Exception as e:
            logger.error(f"Erreur lors de la synchronisation : {e}")
            return {"success": False, "error": str(e)}


