from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import List, Optional
from datetime import datetime
import uuid
import time
import pandas as pd
import json
import os
import subprocess
import threading
from app.models.dispatch import (
    Course, CourseGroupe, Chauffeur, ChauffeurAffectation,
    AdresseGps, TimeWindowParams, Affectation, AffectationCreate, AffectationUpdate
)
from app.core.auth import get_current_user
from app.db.postgres import PostgresDataSource
from app.core.logger import setup_logger

router = APIRouter(prefix="/dispatch", tags=["dispatch"])
logger = setup_logger(__name__)

# Stockage des tâches en cours et terminées (similaire à l'implémentation Flask)
tasks = {}

@router.get("/courses", response_model=List[Course])
async def get_courses(
    time_window: TimeWindowParams = Depends(),
    current_user: dict = Depends(get_current_user),
    ds: PostgresDataSource = Depends()
):
    """Récupère la liste des courses dans une fenêtre temporelle donnée."""
    query = """
        SELECT * FROM course 
        WHERE date_heure_prise_en_charge BETWEEN :debut AND :fin
        ORDER BY date_heure_prise_en_charge
    """
    params = {
        "debut": time_window.date_heure_debut or datetime.now(),
        "fin": time_window.date_heure_fin or datetime.now()
    }
    courses = await ds.fetch_all(query, params)
    return courses

@router.get("/chauffeurs", response_model=List[Chauffeur])
async def get_chauffeurs(
    current_user: dict = Depends(get_current_user),
    ds: PostgresDataSource = Depends()
):
    """Récupère la liste des chauffeurs disponibles."""
    query = "SELECT * FROM chauffeur WHERE actif = true"
    chauffeurs = await ds.fetch_all(query)
    return chauffeurs

@router.get("/adresses", response_model=List[AdresseGps])
async def get_adresses(
    address: str = Query(..., description="Adresse à rechercher"),
    current_user: dict = Depends(get_current_user),
    ds: PostgresDataSource = Depends()
):
    """Recherche des adresses GPS."""
    query = """
        SELECT * FROM adresse_gps 
        WHERE address ILIKE :search
        LIMIT 5
    """
    params = {"search": f"%{address}%"}
    adresses = await ds.fetch_all(query, params)
    return adresses

@router.post("/affectations/", response_model=Affectation)
async def create_affectation(affectation: AffectationCreate, ds: PostgresDataSource = Depends()):
    """Crée une nouvelle affectation de chauffeur à une course"""
    try:
        # Vérifier si la course existe
        course = await ds.fetch_one(
            "SELECT * FROM courses WHERE id = %s",
            (affectation.course_id,)
        )
        if not course:
            raise HTTPException(status_code=404, detail="Course non trouvée")

        # Vérifier si le chauffeur existe
        chauffeur = await ds.fetch_one(
            "SELECT * FROM chauffeurs WHERE id = %s",
            (affectation.chauffeur_id,)
        )
        if not chauffeur:
            raise HTTPException(status_code=404, detail="Chauffeur non trouvé")

        # Vérifier si le chauffeur est disponible
        if not chauffeur["disponible"]:
            raise HTTPException(status_code=400, detail="Chauffeur non disponible")

        # Créer l'affectation
        query = """
            INSERT INTO affectations (course_id, chauffeur_id, date_affectation, statut)
            VALUES (%s, %s, CURRENT_TIMESTAMP, %s)
            RETURNING *
        """
        result = await ds.execute_transaction(
            query,
            (affectation.course_id, affectation.chauffeur_id, affectation.statut)
        )

        # Mettre à jour le statut du chauffeur
        await ds.execute_transaction(
            "UPDATE chauffeurs SET disponible = false WHERE id = %s",
            (affectation.chauffeur_id,)
        )

        return result

    except Exception as e:
        logger.error(f"Erreur lors de la création de l'affectation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/affectations/", response_model=List[Affectation])
async def get_affectations(ds: PostgresDataSource = Depends()):
    """Récupère toutes les affectations"""
    try:
        query = """
            SELECT a.*, c.adresse_depart, c.adresse_arrivee, ch.nom as chauffeur_nom
            FROM affectations a
            JOIN courses c ON a.course_id = c.id
            JOIN chauffeurs ch ON a.chauffeur_id = ch.id
            ORDER BY a.date_affectation DESC
        """
        return await ds.fetch_all(query)
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des affectations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/affectations/{affectation_id}", response_model=Affectation)
async def get_affectation(affectation_id: int, ds: PostgresDataSource = Depends()):
    """Récupère une affectation spécifique"""
    try:
        query = """
            SELECT a.*, c.adresse_depart, c.adresse_arrivee, ch.nom as chauffeur_nom
            FROM affectations a
            JOIN courses c ON a.course_id = c.id
            JOIN chauffeurs ch ON a.chauffeur_id = ch.id
            WHERE a.id = %s
        """
        result = await ds.fetch_one(query, (affectation_id,))
        if not result:
            raise HTTPException(status_code=404, detail="Affectation non trouvée")
        return result
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'affectation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/affectations/{affectation_id}", response_model=Affectation)
async def update_affectation(
    affectation_id: int,
    affectation: AffectationUpdate,
    ds: PostgresDataSource = Depends()
):
    """Met à jour une affectation"""
    try:
        # Vérifier si l'affectation existe
        existing = await ds.fetch_one(
            "SELECT * FROM affectations WHERE id = %s",
            (affectation_id,)
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Affectation non trouvée")

        # Mettre à jour l'affectation
        query = """
            UPDATE affectations
            SET statut = %s
            WHERE id = %s
            RETURNING *
        """
        result = await ds.execute_transaction(
            query,
            (affectation.statut, affectation_id)
        )

        # Si l'affectation est terminée, libérer le chauffeur
        if affectation.statut == "TERMINEE":
            await ds.execute_transaction(
                "UPDATE chauffeurs SET disponible = true WHERE id = %s",
                (existing["chauffeur_id"],)
            )

        return result

    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour de l'affectation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/affectations/{affectation_id}")
async def delete_affectation(affectation_id: int, ds: PostgresDataSource = Depends()):
    """Supprime une affectation"""
    try:
        # Vérifier si l'affectation existe
        existing = await ds.fetch_one(
            "SELECT * FROM affectations WHERE id = %s",
            (affectation_id,)
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Affectation non trouvée")

        # Libérer le chauffeur
        await ds.execute_transaction(
            "UPDATE chauffeurs SET disponible = true WHERE id = %s",
            (existing["chauffeur_id"],)
        )

        # Supprimer l'affectation
        await ds.execute_transaction(
            "DELETE FROM affectations WHERE id = %s",
            (affectation_id,)
        )

        return {"message": "Affectation supprimée avec succès"}

    except Exception as e:
        logger.error(f"Erreur lors de la suppression de l'affectation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dispatch", response_model=dict)
async def start_dispatch(
    background_tasks: BackgroundTasks,
    date_param: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    ds: PostgresDataSource = Depends()
):
    """Endpoint pour lancer l'exécution du script dispatch.py"""
    # Générer un ID unique pour cette tâche
    task_id = str(uuid.uuid4())

    # Initialiser la tâche
    tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "start_time": time.time(),
        "date_param": date_param
    }

    # Lancer l'exécution en arrière-plan
    background_tasks.add_task(run_dispatch_script, task_id, date_param)

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Tâche de planification lancée avec succès"
    }

@router.get("/status/{task_id}", response_model=dict)
async def check_status(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Endpoint pour vérifier le statut d'une tâche"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")

    task = tasks[task_id]
    response = {
        "task_id": task_id,
        "status": task["status"],
        "elapsed_time": (time.time() - task["start_time"])/60
    }

    # Ajouter des infos supplémentaires selon le statut
    if task["status"] == "completed":
        response["result"] = "success"
        response["message"] = "Planification terminée avec succès"
        response["actual_processing_time"] = task.get("elapsed_time", 0)
    elif task["status"] == "error":
        response["result"] = "error"
        response["message"] = "Erreur lors de la planification"
        response["error_details"] = task.get("error", "Erreur inconnue")

    return response

@router.get("/results_supabase/{task_id}", response_model=dict)
async def get_results_supabase(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    ds: PostgresDataSource = Depends()
):
    """Endpoint pour récupérer les résultats d'une tâche terminée depuis Supabase"""
    try:
        # Récupérer les données de la tâche depuis Supabase
        query = """
            SELECT * FROM tasks WHERE id = %s
        """
        task_data = await ds.fetch_one(query, (task_id,))
        
        if not task_data:
            # Si la tâche n'est pas dans Supabase, vérifier le statut local
            return await check_status(task_id)
        
        response_data = {
            "task_id": task_id,
            "status": task_data.get("status"),
            "elapsed_time": task_data.get("elapsed_time_min")
        }
        
        if task_data.get("status") == "completed":
            response_data.update({
                "result": "success",
                "message": "Planification terminée avec succès",
                "actual_processing_time": task_data.get("elapsed_time_min"),
                "result_file": task_data.get("result_file")
            })
        elif task_data.get("status") == "error":
            response_data.update({
                "result": "error",
                "message": "Erreur lors de la planification",
                "error_details": task_data.get("error")
            })
        
        return response_data
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des résultats depuis Supabase: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/results/{task_id}", response_model=dict)
async def get_results(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Endpoint pour récupérer les résultats d'une tâche terminée"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")

    task = tasks[task_id]

    if task["status"] != "completed":
        return {
            "task_id": task_id,
            "status": task["status"],
            "elapsed_time": ((time.time() - task["start_time"])/60),
            "message": "Les résultats ne sont pas encore disponibles"
        }

    # Lire le fichier CSV de résultats
    try:
        results_file = task.get("result_file", "affectations_groupes_chauffeurs_final.csv")
        df = pd.read_csv(results_file)
        results = df.to_dict(orient='records')

        return {
            "task_id": task_id,
            "status": "completed",
            "results": results,
            "elapsed_time": ((time.time() - task["start_time"])/60),
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Erreur lors de la lecture des résultats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def run_dispatch_script(task_id: str, date_param: Optional[str] = None):
    """Exécute le script dispatch.py en arrière-plan"""
    try:
        # Mise à jour du statut
        tasks[task_id]["status"] = "running"
        
        # Suppression du fichier s'il existe déjà
        output_file = "affectations_groupes_chauffeurs_final.csv"
        if os.path.exists(output_file):
            os.remove(output_file)

        # Commande pour exécuter le script dispatch.py
        cmd = ["python", "flask_app/dispatch.py"]

        # Ajouter la date en paramètre si fournie
        if date_param:
            cmd.append(date_param)

        # Exécuter le script et capturer sa sortie
        start_time = time.time()
        process = subprocess.run(cmd, capture_output=True, text=True)
        elapsed_time = time.time() - start_time

        # Enregistrer dans Supabase
        if process.returncode == 0:
            if os.path.exists(output_file):
                task = tasks[task_id]
                results_file = task.get("result_file", "affectations_groupes_chauffeurs_final.csv")
                df = pd.read_csv(results_file)
                results = df.to_dict(orient='records')
                # Transformer en JSON string
                results_json = json.dumps(results, ensure_ascii=False)  # UTF-8 support
                
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["result_file"] = output_file
                tasks[task_id]["output"] = process.stdout
                tasks[task_id]["elapsed_time"] = elapsed_time/60
                tasks[task_id]["results"] = results_json
                
                # Sauvegarder dans Supabase
                await save_task_to_supabase(
                    task_id, "completed", tasks[task_id]["start_time"], 
                    elapsed_time, output_file, process.stdout, None, results_json
                )
            else:
                tasks[task_id]["status"] = "error"
                tasks[task_id]["error"] = "Le fichier de résultats n'a pas été généré"
                await save_task_to_supabase(
                    task_id, "error", tasks[task_id]["start_time"], 
                    elapsed_time, None, None, "Le fichier de résultats n'a pas été généré"
                )
        else:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["error"] = process.stderr
            await save_task_to_supabase(
                task_id, "error", tasks[task_id]["start_time"], 
                elapsed_time, None, process.stdout, process.stderr
            )

    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["error"] = str(e)
        await save_task_to_supabase(
            task_id, "error", tasks[task_id]["start_time"], 
            time.time() - tasks[task_id]["start_time"], None, None, str(e)
        )

async def save_task_to_supabase(task_id, status, start_time, elapsed_time, result_file, output, error, results=None):
    """Sauvegarde les informations de la tâche dans Supabase"""
    try:
        # Convertir le timestamp UNIX en format ISO 8601
        start_time_iso = datetime.utcfromtimestamp(start_time).isoformat()
        
        # Insérer ou mettre à jour la tâche dans Supabase
        query = """
            INSERT INTO tasks (id, status, start_time, elapsed_time_min, result_file, output, error, results)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET status = EXCLUDED.status,
                elapsed_time_min = EXCLUDED.elapsed_time_min,
                result_file = EXCLUDED.result_file,
                output = EXCLUDED.output,
                error = EXCLUDED.error,
                results = EXCLUDED.results
        """
        
        # Utiliser PostgresDataSource pour exécuter la requête
        ds = PostgresDataSource()
        await ds.execute_transaction(
            query,
            (task_id, status, start_time_iso, elapsed_time/60, result_file, output, error, results)
        )
        
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde de la tâche dans Supabase: {str(e)}")
        # Ne pas lever d'exception pour éviter d'interrompre le processus principal 