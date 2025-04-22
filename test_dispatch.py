import os
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Optional

# Configuration des logs AVANT les imports
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)  # Crée le dossier si inexistant

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'dispatch.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Imports après la configuration des logs
from app.db.postgres import PostgresDataSource
from flask_app.dispatch import solve_dispatch_problem
from app.core.course_processor import CourseProcessor

async def update_courses_and_dispatch(ds: PostgresDataSource, date_param=None):
    """Orchestration complète du processus"""
    try:
        # 1. Mise à jour des courses
        processor = CourseProcessor(ds)
        courses = await ds.fetch_all("""
                SELECT  c.course_id
                FROM course c
                LEFT JOIN coursecalcul cc ON c.hash_route = cc.hash_route
                where cc.duree_trajet_min is null 
                or cc.points_passage_coords is null 
                or c.hash_route is null 
                or c.hash_route = ''
        """)  
        
        for course in courses:
            try:
                await processor.process_course(course['course_id'])
                logger.info(f"Course {course['course_id']} traitée")
            except Exception as e:
                logger.error(f"Erreur course {course['course_id']}: {str(e)}")
                continue

        # 2. Exécution du dispatch
        logger.info("Lancement du dispatch...")
        await solve_dispatch_problem(ds, date_param)
        
    except Exception as e:
        logger.error(f"Échec critique: {str(e)}", exc_info=True)
        raise

async def main(date_param=None):
    ds = PostgresDataSource()
    try:
        await update_courses_and_dispatch(ds, date_param)
    finally:
        await ds.close()

if __name__ == "__main__":
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
