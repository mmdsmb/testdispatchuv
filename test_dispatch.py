import asyncio
import logging
from typing import Optional
from app.db.postgres import PostgresDataSource
from app.core.course_processor import CourseProcessor
from app.core.dispatch_solver import solve_dispatch_problem
from datetime import datetime

# Configuration globale
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Désactive les logs des bibliothèques externes
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("app.db.postgres").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

async def update_courses_and_dispatch(
    ds: PostgresDataSource, 
    date_begin: Optional[str] = None,
    date_end: Optional[str] = None,
    milp_time_limit: int = 300
) -> None:
    """Orchestration complète du processus"""
    try:
        # 1. Mise à jour des courses
        processor = CourseProcessor(ds)
        courses = await ds.fetch_all("""
            SELECT c.course_id
            FROM course c
            LEFT JOIN coursecalcul cc ON c.hash_route = cc.hash_route
            WHERE c.hash_route IS NULL OR c.hash_route = ''
            OR cc.duree_trajet_min IS NULL OR cc.distance_routiere_km IS NULL
            OR cc.points_passage_coords IS NULL OR cc.distance_vol_oiseau_km IS NULL
            OR cc.duree_trajet_secondes IS NULL OR cc.points_passage IS NULL
        """)
        
        logger.info(f"Nombre de courses à traiter: {len(courses)}")
        
        for course in courses:
            try:
                await processor.process_course(course['course_id'])
                logger.info(f"Course {course['course_id']} traitée avec succès")
            except Exception as e:
                logger.error(f"Erreur traitement course {course['course_id']}: {str(e)}")

        # 2. Exécution du dispatch
        logger.info("Début du processus de dispatch...")
        assignments = await solve_dispatch_problem(ds, date_begin, date_end, milp_time_limit)
        logger.info(f"Dispatch terminé avec {len(assignments)} affectations")

    except Exception as e:
        logger.error(f"Échec critique: {str(e)}", exc_info=True)
        raise

async def main(date_begin: Optional[str] = None, date_end: Optional[str] = None, milp_timeout: int = 300) -> None:
    """Point d'entrée principal"""
    ds = PostgresDataSource()
    try:
        await update_courses_and_dispatch(ds, date_begin, date_end, milp_timeout)
    finally:
        await ds.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Orchestrateur de traitement des courses")
    
    # Modifier ces lignes pour gérer les espaces dans les dates/heures
    parser.add_argument('--date_begin', nargs='+', help="Date et heure de début (format: 'YYYY-MM-DD HH:MM:SS')")
    parser.add_argument('--date_end', nargs='+', help="Date et heure de fin (format: 'YYYY-MM-DD HH:MM:SS')")
    parser.add_argument("--milp_timeout", type=int, help="Timeout MILP en secondes (défaut: 300)", default=300)
    
    args = parser.parse_args()
    
    # Reconstruire les chaînes de date/heure
    args.date_begin = ' '.join(args.date_begin) if args.date_begin else None
    args.date_end = ' '.join(args.date_end) if args.date_end else None
    
    # Validation du format des dates
    if args.date_begin:
        try:
            datetime.strptime(args.date_begin, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.error("Format de date_begin invalide. Utilisez YYYY-MM-DD HH:MM:SS")
            exit(1)
    
    if args.date_end:
        try:
            datetime.strptime(args.date_end, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.error("Format de date_end invalide. Utilisez YYYY-MM-DD HH:MM:SS")
            exit(1)
    
    try:
        asyncio.run(main(args.date_begin, args.date_end, args.milp_timeout))
    except KeyboardInterrupt:
        logger.info("Interruption manuelle")
    except Exception as e:
        logger.critical(f"Erreur non gérée: {str(e)}", exc_info=True)