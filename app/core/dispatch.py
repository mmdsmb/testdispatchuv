import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pulp
import numpy as np
from app.db.postgres import PostgresDataSource

logger = logging.getLogger(__name__)

async def prepare_demandes(ds: PostgresDataSource, date_begin: Optional[str], date_end: Optional[str]) -> List[Dict[str, Any]]:
    """Prépare les demandes de courses pour le dispatch"""
    try:
        query = """
            SELECT c.*, cg.groupe_id
            FROM course c
            LEFT JOIN courseGroupe cg ON c.id = cg.course_id
            WHERE c.statut = 'EN_ATTENTE'
        """
        params = {}
        if date_begin:
            query += " AND c.date_heure_prise_en_charge >= %s"
            params['date_begin'] = date_begin
        if date_end:
            query += " AND c.date_heure_prise_en_charge <= %s"
            params['date_end'] = date_end
        
        courses = await ds.fetch_all(query, params)
        return [dict(course) for course in courses]
    except Exception as e:
        logger.error(f"Erreur lors de la préparation des demandes: {str(e)}")
        raise

async def prepare_chauffeurs(ds: PostgresDataSource, date_begin: Optional[str], date_end: Optional[str]) -> List[Dict[str, Any]]:
    """Prépare les chauffeurs disponibles pour le dispatch"""
    try:
        query = """
            SELECT c.*
            FROM chauffeur c
            WHERE c.actif = true
        """
        chauffeurs = await ds.fetch_all(query)
        return [dict(chauffeur) for chauffeur in chauffeurs]
    except Exception as e:
        logger.error(f"Erreur lors de la préparation des chauffeurs: {str(e)}")
        raise

async def solve_MILP(demandes: List[Dict[str, Any]], chauffeurs: List[Dict[str, Any]], timeout: int = 300) -> List[Dict[str, Any]]:
    """Résout le problème de dispatch avec un modèle MILP"""
    try:
        logger.info(f"Début de la résolution MILP avec {len(demandes)} demandes et {len(chauffeurs)} chauffeurs")
        
        # Création du problème
        prob = pulp.LpProblem("Dispatch_Problem", pulp.LpMinimize)
        
        # Variables de décision
        x = pulp.LpVariable.dicts("assign",
            ((i, j) for i in range(len(demandes)) for j in range(len(chauffeurs))),
            cat='Binary')
        
        # Fonction objectif - minimiser la somme des distances
        prob += pulp.lpSum(x[i, j] for i in range(len(demandes)) for j in range(len(chauffeurs)))
        
        # Contraintes
        logger.info("Ajout des contraintes...")
        
        # Chaque demande doit être assignée à exactement un chauffeur
        for i in range(len(demandes)):
            prob += pulp.lpSum(x[i, j] for j in range(len(chauffeurs))) == 1
        
        # Chaque chauffeur peut avoir au maximum une demande
        for j in range(len(chauffeurs)):
            prob += pulp.lpSum(x[i, j] for i in range(len(demandes))) <= 1
        
        # Résolution
        logger.info(f"Lancement du solveur avec timeout de {timeout} secondes...")
        solver = pulp.PULP_CBC_CMD(msg=True, timeLimit=timeout)
        prob.solve(solver)
        
        logger.info(f"Statut de la résolution: {pulp.LpStatus[prob.status]}")
        
        if prob.status != pulp.LpStatusOptimal:
            raise Exception(f"Pas de solution optimale trouvée. Statut: {pulp.LpStatus[prob.status]}")
        
        # Construction des affectations
        logger.info("Construction des affectations...")
        assignments = []
        for i in range(len(demandes)):
            for j in range(len(chauffeurs)):
                if x[i, j].value() == 1:
                    assignments.append({
                        "course_id": demandes[i]["id"],
                        "chauffeur_id": chauffeurs[j]["id"],
                        "groupe_id": demandes[i].get("groupe_id")
                    })
        
        logger.info(f"Solution MILP trouvée avec {len(assignments)} affectations")
        return assignments
    except Exception as e:
        logger.error(f"Erreur lors de la résolution MILP: {str(e)}")
        raise

async def heuristic_solution(demandes: List[Dict[str, Any]], chauffeurs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Solution heuristique pour le problème de dispatch"""
    try:
        assignments = []
        chauffeurs_disponibles = chauffeurs.copy()
        
        # Trier les demandes par priorité (par exemple, par date)
        demandes_triees = sorted(demandes, key=lambda x: x["date_heure_prise_en_charge"])
        
        for demande in demandes_triees:
            if not chauffeurs_disponibles:
                break
                
            # Sélectionner le chauffeur le plus proche
            chauffeur = chauffeurs_disponibles.pop(0)
            
            assignments.append({
                "course_id": demande["id"],
                "chauffeur_id": chauffeur["id"],
                "groupe_id": demande.get("groupe_id")
            })
        
        return assignments
    except Exception as e:
        logger.error(f"Erreur lors de la solution heuristique: {str(e)}")
        raise

async def process_uncovered_groups(ds: PostgresDataSource, assignments: List[Dict[str, Any]], date_begin: Optional[str], date_end: Optional[str]):
    """Traite les groupes de courses non couverts"""
    try:
        # Récupérer tous les groupes
        query = """
            SELECT DISTINCT groupe_id
            FROM courseGroupe
            WHERE groupe_id IS NOT NULL
        """
        groupes = await ds.fetch_all(query)
        
        # Identifier les groupes couverts
        groupes_couverts = set(ass.get("groupe_id") for ass in assignments if ass.get("groupe_id"))
        
        # Traiter les groupes non couverts
        for groupe in groupes:
            if groupe["groupe_id"] not in groupes_couverts:
                logger.warning(f"Groupe non couvert: {groupe['groupe_id']}")
                # Ici, vous pouvez ajouter une logique spécifique pour traiter les groupes non couverts
    except Exception as e:
        logger.error(f"Erreur lors du traitement des groupes non couverts: {str(e)}")
        raise 