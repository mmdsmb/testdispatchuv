import asyncio
from app.core.course_processor import CourseProcessor
from app.core.config import settings
from app.db.postgres import PostgresDataSource

async def main():
    try:
        # Initialiser PostgresDataSource
        db = PostgresDataSource()  # Pas besoin de paramètres, ils sont dans settings
        
        # Initialiser CourseProcessor avec PostgresDataSource
        processor = CourseProcessor(db)

        # Définir les dates
        date_debut = "2024-05-01"
        date_fin = "2024-05-31"

        # Vérifier la connexion avec execute_query
        test_query = 'SELECT COUNT(*) as count FROM "Hotes" where evenement_annee = 2024;'
        result = await db.execute_query(test_query)
        print(f"Nombre d'entrées dans la table Hotes : {result[0][0]}")

        # Générer les courses
        courses_df = await processor.genererCourse(date_debut, date_fin)
        print(f"Courses générées avec succès : {len(courses_df)} courses")


    except Exception as e:
        print(f"Erreur : {e}")
    finally:
        await db.disconnect()  # Utilisation de disconnect() au lieu de close()

if __name__ == "__main__":
    asyncio.run(main())
