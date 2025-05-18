import asyncio
import psycopg
import os
import hashlib
from dotenv import load_dotenv
from psycopg.rows import dict_row
from datetime import datetime
import logging
from app.db.postgres import PostgresDataSource
import re

# Pour Windows : nécessaire avec psycopg async
import sys
if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()
DB_URL = os.getenv("SUPABASE_POOL_CONN")
JOURS = [22, 23, 24, 25]

logger = logging.getLogger(__name__)

# Initialize the data source
data_source = PostgresDataSource()

def hash_adresse(email, code_postal):
    return hashlib.sha256(f"{email}_{code_postal}".encode()).hexdigest()



async def transform_data():
    await data_source.connect()
    try:
        # Recreate the chauffeur table (unchanged)
        await data_source.execute_query("""
            CREATE TABLE IF NOT EXISTS chauffeur (
                chauffeur_id SERIAL PRIMARY KEY,
                email TEXT,
                prenom_nom TEXT,
                nombre_place INT,
                telephone TEXT,
                carburant TEXT,
                adresse TEXT,
                code_postal TEXT,
                commentaires TEXT,
                actif BOOLEAN,
                avec_voiture BOOLEAN
            )
        """)

        # Recreate the dispochauffeur table (unchanged)
        await data_source.execute_query("""
            CREATE TABLE IF NOT EXISTS dispochauffeur (
                dispo_id SERIAL PRIMARY KEY,
                chauffeur_id INT REFERENCES chauffeur(chauffeur_id),
                date_debut TIMESTAMPTZ,
                date_fin TIMESTAMPTZ
            )
        """)

        print("✔ Tables recréées")

        # Load data from the bronze table
        rows = await data_source.execute_query("SELECT * FROM chauffeurbronze")

        for row in rows:
            # Adjust indices based on the CSV structure
            email = row[3]  # Index 3 for email
            prenom_nom = row[1]  # Index 1 for prenom_nom
            nombre_places = row[5]  # Index 5 for nombre_places
            telephone = row[2]  # Index 2 for telephone
            carburant = row[15] if len(row) > 15 else None  # Index 15 for carburant (optional)
            adresse = None  # Not in CSV, adjust if needed
            code_postal = row[14] if len(row) > 14 else None  # Index 14 for code_postal
            commentaires = row[16] if len(row) > 16 else None  # Index 16 for commentaires (optional)

            full_address = f"{adresse}, {code_postal}" if code_postal else adresse

            # Check if the chauffeur already exists
            existing = await data_source.execute_query(
                "SELECT chauffeur_id FROM chauffeur WHERE email = %s", (email,)
            )

            if existing:
                chauffeur_id = existing[0][0]
                print(f"⚠ Déjà existant : {prenom_nom} (ID {chauffeur_id})")
            else:
                # Insert a new chauffeur
                result = await data_source.execute_query("""
                    INSERT INTO chauffeur (
                        email, prenom_nom, nombre_place, telephone, carburant,
                        adresse, code_postal, commentaires, actif, avec_voiture
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, true)
                    RETURNING chauffeur_id
                """, (
                    email, prenom_nom, int(nombre_places), telephone,
                    carburant, adresse, code_postal, commentaires
                ))
                chauffeur_id = result[0][0]
                print(f"➕ Inséré : {prenom_nom} (ID {chauffeur_id})")

            # Insert availability (unchanged)
            for jour in JOURS:
                BASE_DATE = f"2025-05-{jour:02d}"
                date_debut_str = row[6 + 2 * (jour - JOURS[0])]  # Index 6 for disponible_22_debut
                date_fin_str = row[7 + 2 * (jour - JOURS[0])]  # Index 7 for disponible_22_fin
                #print(f"date_debut_str: {date_debut_str}")
                #print(f"date_fin_str: {date_fin_str}")
                if date_debut_str and date_fin_str:
                    time_pattern = re.compile(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')
                    if not (time_pattern.match(date_debut_str) and time_pattern.match(date_fin_str)):
                        logger.warning(f"Format d'heure invalide pour {prenom_nom} jour {jour}: début={date_debut_str}, fin={date_fin_str}")
                        continue

                    date_debut = f"{BASE_DATE} {date_debut_str}"
                    date_fin = f"{BASE_DATE} {date_fin_str}"

                    try:
                        date_debut = datetime.fromisoformat(date_debut)
                        date_fin = datetime.fromisoformat(date_fin)

                        await data_source.execute_query("""
                            INSERT INTO dispochauffeur (chauffeur_id, date_debut, date_fin)
                            VALUES (%s, %s, %s)
                        """, (chauffeur_id, date_debut, date_fin))

                    except Exception as e:
                        logger.error(f"Erreur de format date pour {prenom_nom} jour {jour}: {e}")

        await data_source.execute_query("COMMIT")
        print("✔ Données commitées")
    finally:
        await data_source.disconnect()


if __name__ == "__main__":
    asyncio.run(transform_data())
