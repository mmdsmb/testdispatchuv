import asyncio
import logging
from typing import Optional
from app.db.postgres import PostgresDataSource
from app.core.course_processor import CourseProcessor
from flask_app.dispatch import solve_dispatch_problem

# Configuration globale
logging.basicConfig(
    level=logging.INFO,  # Niveau INFO (ignore DEBUG)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Désactive les logs des bibliothèques externes et de la base de données
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("app.db.postgres").setLevel(logging.WARNING)  # Désactive les logs DEBUG de PostgreSQL

logger = logging.getLogger(__name__)

async def update_courses_and_dispatch(ds: PostgresDataSource, date_param: Optional[str] = None) -> None:
    """Orchestration complète du processus de mise à jour des courses et du dispatch"""
    try:
        # 1. Mise à jour des courses
        processor = CourseProcessor(ds)
        
        # Récupérer les courses à traiter
        courses = await ds.fetch_all("""
            SELECT c.course_id
            FROM course c
            LEFT JOIN coursecalcul cc ON c.hash_route = cc.hash_route
            WHERE  c.hash_route is null 
            OR c.hash_route = ''
            OR cc.duree_trajet_min is null 
            OR cc.distance_routiere_km is null
            OR cc.points_passage_coords is null
            OR cc.distance_vol_oiseau_km is null
            OR cc.duree_trajet_secondes is null
            OR cc.points_passage is null

        """)
        
        logger.info(f"Nombre de courses à traiter: {len(courses)}")
        
        # Traiter chaque course
        for course in courses:
            try:
                await processor.process_course(course['course_id'])
                logger.info(f"Course {course['course_id']} traitée avec succès")
            except Exception as e:
                logger.error(f"Erreur lors du traitement de la course {course['course_id']}: {str(e)}")
                continue

        # 2. Exécution du dispatch
        logger.info("Début de solve_dispatch_problem()")
        
        await solve_dispatch_problem(ds, date_param)
        
        # Log de succès
        logger.info("solve_dispatch_problem() terminé avec succès")
        
    except Exception as e:
        # Log d'échec détaillé
        logger.error(f"Échec critique dans solve_dispatch_problem(): {str(e)}", exc_info=True)
        raise

async def main(date_param: Optional[str] = None) -> None:
    """Point d'entrée principal"""
    ds = PostgresDataSource()
    try:
        await update_courses_and_dispatch(ds, date_param)
    finally:
        await ds.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Orchestrateur de traitement des courses")
    parser.add_argument("--date", 
                       help="Date de traitement au format YYYY-MM-DD",
                       default=None)
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args.date))
    except KeyboardInterrupt:
        logger.info("Interruption manuelle du processus")
    except Exception as e:
        logger.critical(f"Erreur non gérée: {str(e)}", exc_info=True)
        raise