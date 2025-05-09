from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
import pandas as pd
import gdown
import logging
from supabase import create_client, Client
import os

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
    Hebergeur: str
    RESTAURATION: str
    Telephone_hebergeur: str = Field(..., alias="Telephone-hebergeur")
    Adresse_hebergement: str = Field(..., alias="Adresse-hebergement")
    Retour_date: Optional[str] = Field(None, alias="Retour-date")
    Nombre_prs_Ret: Optional[str] = Field(None, alias="Nombre-prs-Ret")
    Retour_vol: Optional[str] = Field(None, alias="Retour-vol")
    Retour_heure: Optional[str] = Field(None, alias="Retour-heure")
    Retour_Lieux: Optional[str] = Field(None, alias="Retour-Lieux")
    Destination: Optional[str]
    Chauffeur: Optional[str]

    class Config:
        allow_population_by_field_name = True

class HotesSync:
    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv('SUPABASE_URL'),
            os.getenv('SUPABASE_KEY')
        )

    def download_from_drive(self, file_id: str, output_path: str = 'hotes.xlsx') -> str:
        """Télécharge le fichier depuis Google Drive"""
        try:
            url = f'https://drive.google.com/uc?id={file_id}'
            gdown.download(url, output_path, quiet=False)
            logger.info(f"Fichier téléchargé : {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Erreur de téléchargement : {e}")
            raise

    def read_excel(self, file_path: str) -> List[Hotes]:
        """Lit et valide le fichier Excel"""
        try:
            df = pd.read_excel(
                file_path,
                converters={
                    'Arrivee-date': str,
                    'Retour-date': str
                }
            )
            df = df.where(pd.notnull(df), None)
            df.rename(columns=lambda x: x.replace('-', '_'), inplace=True)
            return [Hotes(**row) for _, row in df.iterrows()]
        except Exception as e:
            logger.error(f"Erreur de lecture : {e}")
            raise

    async def get_existing_hosts(self) -> Dict[int, Dict]:
        """Récupère les hôtes existants depuis Supabase"""
        try:
            response = self.supabase.table('hotes').select('*').execute()
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
                for field in host.__fields__:
                    if isinstance(existing.get(field), datetime):
                        existing[field] = existing[field].strftime('%d-%m-%Y')

                if host_dict != existing:
                    changes['to_update'].append({
                        'id': host.ID,
                        'changes': {
                            field: {'old': existing.get(field), 'new': value}
                            for field, value in host_dict.items()
                            if field != 'ID' and existing.get(field) != value
                        }
                    })
                else:
                    changes['unchanged'].append(host.ID)
        
        logger.info(f"Changements détectés : {len(changes['to_insert'])} insertions, {len(changes['to_update'])} mises à jour")
        return changes

    async def apply_changes(self, changes: Dict) -> Dict:
        """Applique les changements dans Supabase"""
        try:
            if changes['to_insert']:
                self.supabase.table('hotes').insert(changes['to_insert']).execute()
                logger.info(f"{len(changes['to_insert'])} nouveaux hôtes insérés")

            for update in changes['to_update']:
                self.supabase.table('hotes').update(update['changes']).eq('ID', update['id']).execute()
                logger.info(f"Mise à jour de l'hôte ID {update['id']}")

            return {
                'success': True,
                'inserted': len(changes['to_insert']),
                'updated': len(changes['to_update'])
            }
        except Exception as e:
            logger.error(f"Erreur lors de l'application des changements : {e}")
            return {'success': False, 'error': str(e)}

    async def sync(self, file_id: str, auto_apply: bool = False) -> Dict:
        """Workflow complet de synchronisation"""
        try:
            file_path = self.download_from_drive(file_id)
            file_hosts = self.read_excel(file_path)
            existing_hosts = await self.get_existing_hosts()
            changes = self.compare_data(file_hosts, existing_hosts)
            
            if auto_apply:
                return await self.apply_changes(changes)
            
            return {
                'timestamp': datetime.now().isoformat(),
                'changes': changes,
                'stats': {
                    'total': len(file_hosts),
                    'to_insert': len(changes['to_insert']),
                    'to_update': len(changes['to_update']),
                    'unchanged': len(changes['unchanged'])
                }
            }
        except Exception as e:
            logger.error(f"Erreur dans le flux principal : {e}")
            return {'success': False, 'error': str(e)}
