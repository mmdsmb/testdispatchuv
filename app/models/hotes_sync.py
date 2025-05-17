import pandas as pd
import logging
import os
import base64
from datetime import datetime
from tempfile import NamedTemporaryFile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from app.core.config import settings
from app.db.postgres import PostgresDataSource
from app.core.utils import save_and_upload_to_drive

logger = logging.getLogger(__name__)

class HotesSynchronizer:
    def __init__(self, ds: PostgresDataSource):
        self.ds = ds
        self.drive_service = self._authenticate_drive()
        self.col_mapping = {
            'ID': 'ID',
            'Prenom-Nom': 'Prenom-Nom',
            'Telephone': 'Telephone',
            'VIP': 'vip',
            'Nombre-prs-AR': 'Nombre-prs-AR',
            'Provenance': 'Provenance',
            'Arrivee-date': 'Arrivee-date',
            'Arrivee-vol': 'Arrivee-vol',
            'Arrivee-heure': 'Arrivee-heure',
            'Arrivee-Lieux': 'Arrivee-Lieux',
            'Transport_Aller': 'transport_aller',
            'Hebergeur': 'Hebergeur',
            'RESTAURATION': 'RESTAURATION',
            'Telephone-hebergeur': 'Telephone-hebergeur',
            'Adresse-hebergement': 'Adresse-hebergement',
            'Retour-date': 'Retour-date',
            'Nombre-prs-Ret': 'Nombre-prs-Ret',
            'Retour-vol': 'Retour-vol',
            'Retour-heure': 'Retour-heure',
            'Retour-Lieux': 'Retour-Lieux',
            'Destination': 'Destination',
            'Transport_retour': 'transport_retour',
            'Chauffeur': 'Chauffeur'
        }

    async def sync(self, use_online: bool = True):
        """Lance la synchronisation complète"""
        try:
            df = await self._load_data(use_online)
            df = self._clean_data(df)
            await self._save_data(df)
            return True
        except Exception as e:
            logger.error(f"Erreur de synchronisation : {str(e)}")
            return False

    def _authenticate_drive(self):
        """Authentification avec le compte de service Google Drive"""
        creds_base64 = settings.GOOGLE_CREDENTIALS_BASE64
        if not creds_base64:
            raise ValueError("GOOGLE_CREDENTIALS_BASE64 non défini")

        try:
            creds_json = base64.b64decode(creds_base64).decode("utf-8")
            with NamedTemporaryFile(suffix=".json", mode="w", delete=False) as temp_file:
                temp_file.write(creds_json)
                temp_file_path = temp_file.name

            creds = service_account.Credentials.from_service_account_file(temp_file_path)
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Erreur d'authentification Drive : {e}")
            raise

    def download_from_drive(self, file_id: str, output_path: str) -> str:
        """Télécharge un fichier Google Drive en XLSX"""
        try:
            request = self.drive_service.files().export_media(
                fileId=file_id,
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            with open(output_path, 'wb') as f:
                f.write(request.execute())
            logger.info(f"Fichier téléchargé : {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Erreur de téléchargement Drive : {e}")
            raise

    async def _load_data(self, use_online: bool):
        """Charge les données depuis la source sélectionnée"""
        if use_online:
            file_id = os.getenv('HOTES_FILE_ID')
            if not file_id:
                raise ValueError("HOTES_FILE_ID manquant dans .env")
            
            self.download_from_drive(
                file_id=file_id,
                output_path=settings.HOTES_LOCAL_FILENAME
            )
        
        return pd.read_excel(settings.HOTES_LOCAL_FILENAME)

    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Nettoie les données tout en texte"""
        # Renommage des colonnes
        df = df.rename(columns=self.col_mapping)
        
        # Conversion de toutes les colonnes en texte
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
        
        # Nettoyage spécifique
        df = self._clean_dates(df)
        
        return df.replace({'nan': None, 'None': None, '': None})

    async def _save_data(self, df: pd.DataFrame):
        """Sauvegarde les données dans PostgreSQL et exporte les lignes sans ID dans un fichier Excel."""
        query = """
            INSERT INTO "Hotes" (
                "ID", "Prenom-Nom", "Telephone", vip, "Nombre-prs-AR",
                "Provenance", "Arrivee-date", "Arrivee-vol", "Arrivee-heure",
                "Arrivee-Lieux", "transport_aller", "Hebergeur", "RESTAURATION",
                "Telephone-hebergeur", "Adresse-hebergement", "Retour-date",
                "Nombre-prs-Ret", "Retour-vol", "Retour-heure", "Retour-Lieux",
                "Destination", "transport_retour", "Chauffeur"
            ) VALUES (
                %s , %s, %s, %s, %s ,
                %s, %s, %s, %s,
                %s,%s, %s, %s,
                %s, %s, %s,
                %s , %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT ("ID") DO UPDATE SET
                "Prenom-Nom" = EXCLUDED."Prenom-Nom",
                "Telephone" = EXCLUDED."Telephone",
                vip = EXCLUDED.vip,
                "Nombre-prs-AR" = EXCLUDED."Nombre-prs-AR" ,
                "Provenance" = EXCLUDED."Provenance",
                "Arrivee-date" = EXCLUDED."Arrivee-date",
                "Arrivee-vol" = EXCLUDED."Arrivee-vol",
                "Arrivee-heure" = EXCLUDED."Arrivee-heure",
                "Arrivee-Lieux" = EXCLUDED."Arrivee-Lieux",
                "transport_aller" = EXCLUDED."transport_aller",
                "Hebergeur" = EXCLUDED."Hebergeur",
                "RESTAURATION" = EXCLUDED."RESTAURATION",
                "Telephone-hebergeur" = EXCLUDED."Telephone-hebergeur",
                "Adresse-hebergement" = EXCLUDED."Adresse-hebergement",
                "Retour-date" = EXCLUDED."Retour-date",
                "Nombre-prs-Ret" = EXCLUDED."Nombre-prs-Ret",
                "Retour-vol" = EXCLUDED."Retour-vol",
                "Retour-heure" = EXCLUDED."Retour-heure",
                "Retour-Lieux" = EXCLUDED."Retour-Lieux",
                "Destination" = EXCLUDED."Destination",
                "transport_retour" = EXCLUDED."transport_retour",
                "Chauffeur" = EXCLUDED."Chauffeur"
        """

        required_columns = [
            'ID', 'Prenom-Nom', 'Telephone', 'vip', 'Nombre-prs-AR',
            'Provenance', 'Arrivee-date', 'Arrivee-vol', 'Arrivee-heure',
            'Arrivee-Lieux', 'transport_aller', 'Hebergeur', 'RESTAURATION',
            'Telephone-hebergeur', 'Adresse-hebergement', 'Retour-date',
            'Nombre-prs-Ret', 'Retour-vol', 'Retour-heure', 'Retour-Lieux',
            'Destination', 'transport_retour', 'Chauffeur'
        ]

        # Convertir les données en listes de tuples
        records = df[required_columns].apply(lambda row: tuple(row), axis=1).tolist()

        # Fonction pour nettoyer l'ID
        def clean_id(value):
            if pd.isna(value) or value in (None, "", "nan"):
                return None
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return None

        # Séparer les lignes valides et les lignes sans ID
        valid_records = []
        error_records = []

        for record in records:
            cleaned_id = clean_id(record[0])
            if cleaned_id is not None:
                valid_records.append((cleaned_id, *record[1:]))
            else:
                error_records.append(record)

        # Sauvegarder les lignes valides
        if valid_records:
            await self.ds.execute_transaction([(query, record) for record in valid_records])

        # Exporter les lignes sans ID dans un fichier Excel
        if error_records:
            error_df = pd.DataFrame(error_records, columns=required_columns)
            #error_file_path = "erreurs_hotes.xlsx"
            #error_df.to_excel(error_file_path, index=False)
            #logger.error(f"{len(error_records)} lignes sans ID exportées dans {error_file_path}")
            # Uploader le fichier d'erreurs vers Drive
            try:
         
                folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')  # ID du dossier parent dans Drive
                logger.error("GOOGLE_DRIVE_FOLDER_ID non trouvé dans le fichier .env")
                await save_and_upload_to_drive(
                    df=error_df,
                    folder_id=folder_id,
                    file_prefix="erreurs_hotes",
                    subfolder_name="hotes",
                    format_excel=True,
                    index=False
                )
            except Exception as e:
                logger.error(f"Échec de l'upload des erreurs hotes vers Drive : {e}")
    def _clean_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Nettoie les dates au format YYYY-MM-DD"""
        date_cols = ['Arrivee-date', 'Retour-date']
        for col in date_cols:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
        return df