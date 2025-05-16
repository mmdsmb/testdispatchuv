import hashlib
import logging
from typing import Optional, Tuple, List, Any
from fastapi import HTTPException
from app.db.postgres import PostgresDataSource
from app.core.geocoding import geocoding_service

logger = logging.getLogger(__name__)

class ChauffeurProcessor:
    def __init__(self, ds: PostgresDataSource):
        self.ds = ds

    def _generate_address_hash(self, address: str) -> str:
        """Génère un hash MD5 standardisé pour les adresses"""
        return hashlib.md5(address.strip().lower().encode('utf-8')).hexdigest()

    async def process_chauffeur_addresses(self) -> None:
        """
        Traite les adresses des chauffeurs et les enregistre dans adresseGps.
        Priorité à l'adresse, puis au code postal si l'adresse est vide.
        Met à jour hash_adresse dans la table chauffeur.
        """
        errors = []
        
        # 1. Récupérer les chauffeurs avec adresse ou code postal mais sans coordonnées
        query = """
            SELECT c.chauffeur_id, c.adresse, c.code_postal, c.hash_adresse
            FROM chauffeur c
            LEFT JOIN adresseGps ag ON c.hash_adresse = ag.hash_address
            WHERE (c.adresse IS NOT NULL OR c.code_postal IS NOT NULL)
            AND (c.hash_adresse IS NULL OR ag.latitude IS NULL OR ag.longitude IS NULL)
        """
        
        try:
            # Utilisation de fetch_all
            chauffeurs = await self.ds.fetch_all(query)
            
            for ch in chauffeurs:
                chauffeur_id = None
                try:
                    # Vérification du type de résultat (dict ou tuple)
                    if isinstance(ch, dict):
                        # Extraction des valeurs par clé
                        chauffeur_id = ch.get('chauffeur_id')
                        adresse = ch.get('adresse')
                        code_postal = ch.get('code_postal')
                        hash_existant = ch.get('hash_adresse')
                    else:
                        # Extraction des valeurs par position
                        chauffeur_id = ch[0] if len(ch) > 0 else None
                        adresse = ch[1] if len(ch) > 1 else None
                        code_postal = ch[2] if len(ch) > 2 else None
                        hash_existant = ch[3] if len(ch) > 3 else None

                    # Validation de l'ID
                    if not chauffeur_id:
                        logger.warning("Chauffeur sans ID - ignoré")
                        continue
                    
                    try:
                        chauffeur_id = int(chauffeur_id)
                    except (ValueError, TypeError):
                        logger.error(f"ID de chauffeur invalide: {chauffeur_id}")
                        continue
                    
                    # Déterminer l'adresse à utiliser
                    address_to_geocode = adresse if adresse and adresse.strip() else code_postal
                    if not address_to_geocode:
                        logger.warning(f"Chauffeur {chauffeur_id} ignoré : adresse et code postal manquants")
                        continue
                    
                    # 2. Générer le hash
                    hash_address = hash_existant or self._generate_address_hash(address_to_geocode)
                    
                    # 3. Vérifier si les coordonnées existent déjà
                    existing_coords = await self.ds.fetch_one(
                        "SELECT latitude, longitude FROM adresseGps WHERE hash_address = %s",
                        (hash_address,)
                    )
                    
                    # Vérification du type de résultat pour existing_coords
                    if existing_coords:
                        if isinstance(existing_coords, dict):
                            lat = existing_coords.get('latitude')
                            lng = existing_coords.get('longitude')
                        else:
                            lat = existing_coords[0] if len(existing_coords) > 0 else None
                            lng = existing_coords[1] if len(existing_coords) > 1 else None
                        
                        if lat is not None and lng is not None:
                            await self.ds.execute_query(
                                "UPDATE chauffeur SET hash_adresse = %s WHERE chauffeur_id = %s",
                                (hash_address, chauffeur_id)
                            )
                            continue
                        
                    # 4. Géocoder l'adresse
                    coords = await geocoding_service.get_coordinates(address_to_geocode)
                    if not coords or None in coords:
                        logger.error(f"Échec du géocodage pour l'adresse: {address_to_geocode}")
                        continue
                    
                    # 5. Enregistrer dans adresseGps
                    await self.ds.execute_transaction([
                        (
                            """
                            INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (hash_address) DO UPDATE
                            SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                            """,
                            (hash_address, address_to_geocode, coords[0], coords[1])
                        )
                    ])
                    
                    # 6. Mettre à jour le hash dans chauffeur
                    await self.ds.execute_query(
                        "UPDATE chauffeur SET hash_adresse = %s WHERE chauffeur_id = %s",
                        (hash_address, chauffeur_id)
                    )
                    
                except Exception as e:
                    logger.error(f"Erreur traitement chauffeur {chauffeur_id if chauffeur_id else 'N/A'}: {str(e)}")
                    errors.append(f"Chauffeur {chauffeur_id if chauffeur_id else 'N/A'}: {str(e)}")
                    try:
                        await self.ds.rollback()
                    except:
                        pass
                    
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des chauffeurs: {str(e)}")
            raise ValueError(f"Erreur initiale: {str(e)}")
        
        if errors:
            raise ValueError(
                f"Échec sur {len(errors)} chauffeurs lors du traitement des adresses:\n"
                + "\n".join(errors)
            )
