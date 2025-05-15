import asyncio
import logging
from typing import Optional
from app.db.postgres import PostgresDataSource
from app.core.course_groupe_processor import CourseGroupeProcessor
from app.core.dispatch_solver import solve_dispatch_problem

logger = logging.getLogger(__name__)

async def process_course_group(processor: CourseGroupeProcessor, groupe_ids: list[str]) -> None:
    """Traite un groupe de courses"""
    for groupe_id in groupe_ids:
        try:
            await processor.process_course_groupe(groupe_id)
            logger.info(f"Groupe {groupe_id} traité avec succès")
        except Exception as e:
            logger.error(f"Erreur traitement groupe {groupe_id}: {str(e)}")

async def run_dispatch_solver_orchestration(
    date_begin: Optional[str] = None,
    date_end: Optional[str] = None,
    milp_time_limit: int = 300
) -> None:
    """Orchestration complète du calcul des groupes et du dispatch"""
    ds = PostgresDataSource()
    try:
        processor = CourseGroupeProcessor(ds)
        groupes = await ds.fetch_all("""
            SELECT cg.groupe_id
            FROM courseGroupe cg
            LEFT JOIN coursecalcul cc ON cg.hash_route = cc.hash_route
            WHERE cg.hash_route IS NULL OR cg.hash_route = ''
            OR cc.duree_trajet_min IS NULL OR cc.distance_routiere_km IS NULL
            OR cc.points_passage_coords IS NULL OR cc.distance_vol_oiseau_km IS NULL
            OR cc.duree_trajet_secondes IS NULL OR cc.points_passage IS NULL
        """)
        logger.info(f"Nombre de groupes à traiter: {len(groupes)}")
        groupe_ids = [groupe['groupe_id'] for groupe in groupes]
        await process_course_group(processor, groupe_ids)
        logger.info("Début du processus de dispatch...")
        assignments = await solve_dispatch_problem(ds, date_begin, date_end, milp_time_limit)
        logger.info(f"Dispatch terminé avec {len(assignments)} affectations")
        return assignments
    except Exception as e:
        logger.error(f"Échec critique: {str(e)}", exc_info=True)
        raise
    finally:
        await ds.close()
