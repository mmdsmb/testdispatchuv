
#script_tranfert_synchro.py

import asyncio
import psycopg
import os
import hashlib
from dotenv import load_dotenv
from psycopg.rows import dict_row
from datetime import datetime

# Pour Windows : nécessaire avec psycopg async
import sys
if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()
DB_URL = os.getenv("SUPABASE_POOL_CONN")
JOURS = [22, 23, 24, 25]

def hash_adresse(email, code_postal):
    return hashlib.sha256(f"{email}_{code_postal}".encode()).hexdigest()

async def transform_data():
    async with await psycopg.AsyncConnection.connect(DB_URL, row_factory=dict_row) as conn:
        async with conn.cursor() as cur:
            # 🔁 Supprimer les tables existantes
            await cur.execute("DROP TABLE IF EXISTS dispochauffeur")
            await cur.execute("DROP TABLE IF EXISTS chauffeur")

            # 🧱 Recréer la table chauffeur
            await cur.execute("""
                CREATE TABLE chauffeur (
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
                    avec_voiture BOOLEAN,
                    hash_adresse TEXT UNIQUE
                )
            """)

            # 🧱 Recréer la table dispochauffeur
            await cur.execute("""
                CREATE TABLE dispochauffeur (
                    dispo_id SERIAL PRIMARY KEY,
                    chauffeur_id INT REFERENCES chauffeur(chauffeur_id),
                    date_debut TIMESTAMPTZ,
                    date_fin TIMESTAMPTZ
                )
            """)

            print("✔ Tables recréées")

            # 🚛 Charger les données depuis la table bronze
            await cur.execute("SELECT * FROM chauffeurbronze")
            rows = await cur.fetchall()

            for row in rows:
                hash_addr = hash_adresse(row['email'], row['code_postal'])

                # Vérifier si le chauffeur existe déjà
                await cur.execute("SELECT chauffeur_id FROM chauffeur WHERE hash_adresse = %s", (hash_addr,))
                existing = await cur.fetchone()

                if existing:
                    chauffeur_id = existing["chauffeur_id"]
                    print(f"⚠ Déjà existant : {row['prenom_nom']} (ID {chauffeur_id})")
                else:
                    # Insérer un nouveau chauffeur
                    await cur.execute("""
                        INSERT INTO chauffeur (
                            email, prenom_nom, nombre_place, telephone, carburant,
                            adresse, code_postal, commentaires, actif, avec_voiture, hash_adresse
                        )
                        VALUES (%s, %s, %s, %s, %s, '', %s, %s, true, true, %s)
                        RETURNING chauffeur_id
                    """, (
                        row['email'], row['prenom_nom'], int(row['nombre_places']), row['telephone'],
                        row['carburant'], row['code_postal'], row['commentaires'], hash_addr
                    ))
                    chauffeur_id = (await cur.fetchone())['chauffeur_id']
                    print(f"➕ Inséré : {row['prenom_nom']} (ID {chauffeur_id})")

                # Insérer les disponibilités
                for jour in JOURS:
                    # Exemple : on suppose que les disponibilités concernent mai 2025
                    BASE_DATE = f"2025-05-{jour:02d}"

                    date_debut_str = row.get(f'disponible_{jour}_debut')
                    date_fin_str = row.get(f'disponible_{jour}_fin')

                    if date_debut_str and date_fin_str:
                        # Concaténer une date avec l'heure
                        date_debut = f"{BASE_DATE} {date_debut_str}"
                        date_fin = f"{BASE_DATE} {date_fin_str}"

                        # Parsing en datetime pour sécurité (ou garder en string avec format SQL-compatible)
                        try:
                            date_debut = datetime.fromisoformat(date_debut)
                            date_fin = datetime.fromisoformat(date_fin)

                            await cur.execute("""
                                INSERT INTO dispochauffeur (chauffeur_id, date_debut, date_fin)
                                VALUES (%s, %s, %s)
                            """, (chauffeur_id, date_debut, date_fin))

                        except Exception as e:
                            print(f"Erreur de format date pour {row['prenom_nom']} jour {jour}: {e}")

        print("Données insérées avec succès.")

if __name__ == "__main__":
    asyncio.run(transform_data())