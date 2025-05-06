from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import Optional
from datetime import datetime
import secrets
import logging
from app.db.postgres import PostgresDataSource
from app.core.course_groupe_processor import CourseGroupeProcessor
from app.core.dispatch_solver_versionAvecVaraibleContrainte import solve_dispatch_problem
from app.core.config import settings

# Configuration du logging
logger = logging.getLogger(__name__)

# Configuration de l'authentification Basic
security = HTTPBasic()

router = APIRouter(prefix="/dispatch", tags=["dispatch"])

# Stockage des tâches en cours
tasks = {}

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Vérifie les identifiants de l'utilisateur"""
    correct_username = secrets.compare_digest(credentials.username, settings.DISPATCH_API_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, settings.DISPATCH_API_PASSWORD)
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

async def process_dispatch_task(
    task_id: str,
    date_begin: Optional[str],
    date_end: Optional[str],
    milp_timeout: int
):
    """Traite une tâche de dispatch en arrière-plan"""
    try:
        # Mise à jour du statut
        tasks[task_id]["status"] = "running"
        
        # Initialisation de la connexion à la base de données
        ds = PostgresDataSource()
        try:
            # 1. Mise à jour des groupes de courses
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
            
            # Traitement des groupes
            groupe_ids = [groupe['groupe_id'] for groupe in groupes]
            for groupe_id in groupe_ids:
                try:
                    await processor.process_course_groupe(groupe_id)
                    logger.info(f"Groupe {groupe_id} traité avec succès")
                except Exception as e:
                    logger.error(f"Erreur traitement groupe {groupe_id}: {str(e)}")
                    continue

            # 2. Exécution du dispatch
            logger.info("Début du processus de dispatch...")
            assignments = await solve_dispatch_problem(ds, date_begin, date_end, milp_timeout)
            logger.info(f"Dispatch terminé avec {len(assignments)} affectations")

            # Mise à jour du statut de la tâche
            tasks[task_id]["status"] = "completed"
            tasks[task_id]["result"] = assignments
            tasks[task_id]["completed_at"] = datetime.now().isoformat()

        finally:
            await ds.close()

    except Exception as e:
        logger.error(f"Erreur lors du traitement de la tâche {task_id}: {str(e)}")
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["completed_at"] = datetime.now().isoformat()

@router.post("/start")
async def start_dispatch(
    background_tasks: BackgroundTasks,
    date_begin: Optional[str] = None,
    date_end: Optional[str] = None,
    milp_timeout: int = 300,
    username: str = Depends(verify_credentials)
):
    """Lance une nouvelle tâche de dispatch"""
    # Validation des dates
    if date_begin:
        try:
            datetime.strptime(date_begin, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Format de date_begin invalide. Utilisez YYYY-MM-DD HH:MM:SS"
            )
    
    if date_end:
        try:
            datetime.strptime(date_end, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Format de date_end invalide. Utilisez YYYY-MM-DD HH:MM:SS"
            )

    # Génération d'un ID unique pour la tâche
    task_id = secrets.token_hex(8)
    
    # Initialisation de la tâche
    tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "date_begin": date_begin,
        "date_end": date_end,
        "milp_timeout": milp_timeout,
        "created_at": datetime.now().isoformat(),
        "created_by": username
    }

    # Lancement du traitement en arrière-plan
    background_tasks.add_task(
        process_dispatch_task,
        task_id,
        date_begin,
        date_end,
        milp_timeout
    )

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Tâche de dispatch lancée avec succès"
    }

@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    username: str = Depends(verify_credentials)
):
    """Récupère le statut d'une tâche de dispatch"""
    if task_id not in tasks:
        raise HTTPException(
            status_code=404,
            detail="Tâche non trouvée"
        )
    
    return tasks[task_id]

@router.get("/tasks")
async def list_tasks(
    username: str = Depends(verify_credentials)
):
    """Liste toutes les tâches de dispatch"""
    return {
        "tasks": [
            {
                "id": task_id,
                "status": task["status"],
                "created_at": task["created_at"],
                "created_by": task["created_by"]
            }
            for task_id, task in tasks.items()
        ]
    } 