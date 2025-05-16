import os
import math
import random
import time
import logging
import pulp
import pandas as pd
from datetime import datetime, timedelta
from itertools import combinations
from geopy.distance import geodesic
from app.db.postgres import PostgresDataSource
from fastapi import HTTPException
import httpx
import hashlib
from typing import Tuple, Optional, List, Dict, Any
from app.core.geocoding import geocoding_service
from app.core.utils import generate_address_hash, save_and_upload_to_drive
from decimal import Decimal  # Ensure this import exists at the top of the file
import json
from app.core.chauffeur_processor import ChauffeurProcessor
from app.core.course_groupe_processor import CourseGroupeProcessor  

# Configuration du logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='dispatch_log.txt',
    filemode='w'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Fonctions auxiliaires
# =============================================================================

async def geocode_address(address: str, postal_code: str = None) -> Tuple[float, float, str]:
    """Géocode une adresse avec gestion d'erreur et fallback manuel"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{address}, {postal_code}" if postal_code else address, 
                       "format": "json", "limit": 1}
            )
            response.raise_for_status()
            data = response.json()
            if data:
                return float(data[0]['lat']), float(data[0]['lon']), data[0]['display_name']
            
        # Fallback si l'API ne retourne rien
        raise ValueError("Aucun résultat de géocodage")
    except Exception as e:
        logger.error(f"Échec du géocodage pour {address}: {e}")
        raise ValueError(f"Impossible de géocoder l'adresse: {address}")

def is_finite_coordinate(*coords):
    """Vérifie que toutes les coordonnées sont définies."""
    return all(pd.notnull(c) for c in coords)

def haversine(lat1, lon1, lat2, lon2):
    """Calcule la distance en kilomètres entre deux points géographiques."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def travel_time_single(chauffeur, groupe):
    """Calcule le temps de trajet ou échoue explicitement"""
    try:
        if not is_finite_coordinate(chauffeur['lat_chauff'], chauffeur['long_chauff'],
                                    groupe['lat_pickup'], groupe['long_pickup'],
                                    groupe['dest_lat'], groupe['dest_lng']):
            raise ValueError("Coordonnées invalides")
        t1 = round(geodesic((chauffeur['lat_chauff'], chauffeur['long_chauff']),
                            (groupe['lat_pickup'], groupe['long_pickup'])).kilometers)
        t2 = round(groupe['duree_trajet_min'])
        t3 = round(geodesic((groupe['dest_lat'], groupe['dest_lng']),
                            (chauffeur['lat_chauff'], chauffeur['long_chauff'])).kilometers)
        return t1 + t2 + t3
    except Exception as e:
        logger.error(f"Erreur de calcul pour {groupe['id']}: {e}")
        raise

def combined_route_cost(chauffeur, g1, g2):
    if abs(g1['t_min'] - g2['t_min']) > 45:
        return None
    D = (chauffeur['lat_chauff'], chauffeur['long_chauff'])
    C1 = (g1['lat_pickup'], g1['long_pickup'])
    C2 = (g2['lat_pickup'], g2['long_pickup'])
    A1 = (g1['dest_lat'], g1['dest_lng'])
    A2 = (g2['dest_lat'], g2['dest_lng'])
    Tsolo1 = travel_time_single(chauffeur, g1)
    Tsolo2 = travel_time_single(chauffeur, g2)
    def t(p, q): return round(geodesic(p, q).kilometers)
    routes = [
        (t(D,C1), t(C1,C2), t(C2,A1), t(A1,A2), t(A2,D)),
        (t(D,C1), t(C1,C2), t(C2,A2), t(A2,A1), t(A1,D)),
        (t(D,C2), t(C2,C1), t(C1,A1), t(A1,A2), t(A2,D)),
        (t(D,C2), t(C2,C1), t(C1,A2), t(A2,A1), t(A1,D)),
    ]
    feasible = []
    for route in routes:
        # on suppose admissible
        feasible.append(sum(route))
    return min(feasible) if feasible else None

# =============================================================================
# Lecture et préparation des données (version PostgresDataSource)
# =============================================================================

async def prepare_demandes(ds: PostgresDataSource, date_begin: Optional[str] = None, date_end: Optional[str] = None):
    """Récupère les courses avec calcul des distances en Python (sans SQL geodesic)"""
    query = """
        SELECT 
            c.groupe_id as id,
            c.nombre_personne as ng,
            c.lieu_prise_en_charge as pickup_address,
            c.destination as dropoff_address,
            ag_pickup.latitude as lat_pickup,
            ag_pickup.longitude as long_pickup,
            ag_dest.latitude as dest_lat,
            ag_dest.longitude as dest_lng,
            c.date_heure_prise_en_charge,
            EXTRACT(EPOCH FROM (c.date_heure_prise_en_charge - NOW()))/60 as t_min,
            cc.duree_trajet_min
        FROM courseGroupe c
        JOIN adresseGps ag_pickup ON c.hash_lieu_prise_en_charge = ag_pickup.hash_address
        JOIN adresseGps ag_dest ON c.hash_destination = ag_dest.hash_address
        LEFT JOIN coursecalcul cc ON c.hash_route = cc.hash_route
    """
    if date_begin and date_end:
        query += " WHERE c.date_heure_prise_en_charge BETWEEN %(date_begin)s AND %(date_end)s"
    elif date_begin:
        query += " WHERE c.date_heure_prise_en_charge >= %(date_begin)s"
    elif date_end:
        query += " WHERE c.date_heure_prise_en_charge <= %(date_end)s"
    
    rows = await ds.fetch_all(query, {
        "date_begin": date_begin,
        "date_end": date_end
    } if date_begin or date_end else {})
    
    if not rows:
        logger.info("Aucune course valide après vérification des coordonnées (prepare_demandes)")
        return []
    
    # Conversion en list[dict] et calcul des durées manquantes
    demandes = []
    for row in rows:
        demande = dict(row)
        if demande['duree_trajet_min'] is None:
            # Calcul de la durée en Python avec geopy.geodesic
            try:
                distance_km = geodesic(
                    (demande['lat_pickup'], demande['long_pickup']),
                    (demande['dest_lat'], demande['dest_lng'])
                ).kilometers
                demande['duree_trajet_min'] = distance_km * 2  # Exemple: 2 min/km
            except Exception as e:
                logger.error(f"Erreur calcul durée pour course {demande['id']}: {e}")
                demande['duree_trajet_min'] = 0  # Valeur par défaut
        
        demandes.append(demande)
    
    return demandes

async def prepare_chauffeurs(ds: PostgresDataSource, date_begin: Optional[str] = None, date_end: Optional[str] = None):
    """Récupère et prépare les chauffeurs disponibles pour une période donnée"""
    query = """
        SELECT 
            c.chauffeur_id as id,
            c.nombre_place as n,
            c.prenom_nom,
            ag.latitude as lat_chauff,
            ag.longitude as long_chauff,
            dc.date_debut as availability_date,
            dc.date_fin as availability_date_end
        FROM chauffeur c
        JOIN dispoChauffeur dc ON c.chauffeur_id = dc.chauffeur_id
        LEFT JOIN adresseGps ag ON c.hash_adresse = ag.hash_address
        WHERE c.actif = true
    """

    params = {}
    
    if date_begin and date_end:
        query += " AND dc.date_debut <= %(date_end)s AND dc.date_fin >= %(date_begin)s"
        params.update({"date_begin": date_begin, "date_end": date_end})
    elif date_begin:
        query += " AND dc.date_fin >= %(date_begin)s"
        params.update({"date_begin": date_begin})
    elif date_end:
        query += " AND dc.date_debut <= %(date_end)s"
        params.update({"date_end": date_end})

    rows = await ds.fetch_all(query, params)
    
    if not rows:
        logger.warning("Aucun chauffeur disponible pour la période spécifiée")
        return []
        
    # Convertir les rows en list[dict] si ce n'est pas déjà le cas
    if isinstance(rows, list) and len(rows) > 0 and not isinstance(rows[0], dict):
        columns = ['id', 'n', 'prenom_nom', 'lat_chauff', 'long_chauff', 'availability_date', 'availability_date_end']
        rows = [dict(zip(columns, row)) for row in rows]
    
    return rows

# =============================================================================
# Précalcul des coûts pour améliorer la performance
# =============================================================================

# =============================================================================
# Fonction pour construire et résoudre le modèle MILP
# =============================================================================
def solve_MILP(groupes, chauffeurs, solo_cost, combo_cost, time_limit):
    
    """Résolution du problème MILP avec logs."""
    logger.info(f"Début de la résolution MILP avec une limite de temps de {time_limit} secondes")
    logger.info(f"Nombre de groupes : {len(groupes)}, Nombre de chauffeurs : {len(chauffeurs)}")
    
    try:    
        group_ids = {g['id'] for g in groupes}
        prob = pulp.LpProblem("Affectation", pulp.LpMinimize)
        x,y = {},{}
        # solo
        for g in groupes:
            for c in chauffeurs:
                if (g['id'],c['id']) in solo_cost:
                    x[(g['id'],c['id'])] = pulp.LpVariable(f"x_{g['id']}_{c['id']}",0,1,pulp.LpBinary)
        # combo filtré
        for (g1,g2,c),cost in combo_cost.items():
            if g1 in group_ids and g2 in group_ids:
                y[(g1,g2,c)] = pulp.LpVariable(f"y_{g1}_{g2}_{c}",0,1,pulp.LpBinary)
        # objectif
        prob += pulp.lpSum([solo_cost[k]*v for k,v in x.items()]+[combo_cost[k]*v for k,v in y.items()])
        # couverture
        cap={c['id']:c['n'] for c in chauffeurs}
        for g in groupes:
            soloCap = pulp.lpSum(c['n']*x[(g['id'],c['id'])] for c in chauffeurs if (g['id'],c['id']) in x)
            comboCap = pulp.lpSum(0.5*cap[k[2]]*v for k,v in y.items() if g['id'] in k[:2])
            prob += soloCap+comboCap>=g['ng']
        # non-chevauchement + max4
        for c in chauffeurs:
            tasks=[]
            for g in groupes:
                if (g['id'],c['id']) in x:
                    s=g['t_min'];f=s+solo_cost[(g['id'],c['id'])]
                    tasks.append((s,f,x[(g['id'],c['id'])]))
            for (g1,g2,cc),v in y.items():
                if cc==c['id']:
                    gA=next(g for g in groupes if g['id']==g1)
                    gB=next(g for g in groupes if g['id']==g2)
                    s=min(gA['t_min'],gB['t_min']);f=s+combo_cost[(g1,g2,cc)]
                    tasks.append((s,f,v))
            for i in range(len(tasks)):
                for j in range(i+1,len(tasks)):
                    if tasks[i][0]<tasks[j][1] and tasks[j][0]<tasks[i][1]:
                        prob += tasks[i][2]+tasks[j][2]<=1
            prob += pulp.lpSum(t[2] for t in tasks)<=4
        # capacité faible
        for g in groupes:
            if g['ng']<=4:
                for c in chauffeurs:
                    if c['n']>4 and (g['id'],c['id']) in x:
                        prob += x[(g['id'],c['id'])]==0
        # combo faible
        for (g1,g2,c),v in y.items():
            gA=next(g for g in groupes if g['id']==g1)
            gB=next(g for g in groupes if g['id']==g2)
            if (gA['ng']<=3 or gB['ng']<=3) and next(ch for ch in chauffeurs if ch['id']==c)['n']>4:
                prob += v==0
        solver = pulp.PULP_CBC_CMD(timeLimit=time_limit,msg=False)
        status=prob.solve(solver)
        return prob,status,x,y
    
    except Exception as e:
        logger.error(f"Erreur lors de la résolution MILP : {e}")
        raise

# =============================================================================
# Méthode heuristique par recuit simulé
# =============================================================================
def heuristic_solution(groupes, chauffeurs, solo_cost, combo_cost, existing=None):
    """
    Recuit simulé pour générer une solution admissible.
    Pour simplifier, ici on construit initialement des affectations solo (en respectant non-chevauchement et max 4 missions)
    puis on applique un recuit sur l'ensemble des groupes (ou uniquement sur ceux non couverts si existing_assignments est fourni).
    """
    
    logger.info("Début de la solution heuristique par recuit simulé")
    logger.info(f"Nombre de groupes à traiter : {len(groupes)}")
    logger.info(f"Nombre de chauffeurs disponibles : {len(chauffeurs)}")
    try:
        if existing is None:
            assign={}
            to_proc=groupes
        else:
            assign={**existing}
            to_proc=[g for g in groupes if g['id'] not in assign or not assign[g['id']]]
        sched={c['id']:[] for c in chauffeurs}
        cnt={c['id']:0 for c in chauffeurs}
        for g in sorted(to_proc, key=lambda g:g['t_min']):
            remaining=g['ng']
            # tri chauffeurs efficients
            for c in sorted(chauffeurs, key=lambda c:-c['n']):
                if remaining<=0: break
                if cnt[c['id']]>=4: continue
                if g['ng']<=4 and c['n']>4: continue
                if (g['id'],c['id']) not in solo_cost: continue
                st=g['t_min'];fi=st+solo_cost[(g['id'],c['id'])]
                if any(not(fi<=s or st>=f) for s,f in sched[c['id']]): continue
                # affecter
                assign.setdefault(g['id'],[]).append({"chauffeur":c['id'],"trajet":"simple"})
                sched[c['id']].append((st,fi))
                cnt[c['id']]+=1
                remaining -= c['n']
        return assign

    except Exception as e:
        logger.error(f"Erreur lors de l'exécution du recuit simulé : {e}")
        raise


def extract_assignments(groupes, chauffeurs, x, y):
    logger.info("Extracting group-driver assignments")
    assignments = {}
    
    # Générer un timestamp unique pour cette session
    session_timestamp = int(time.time())
    
    # Affectations solo
    for g in groupes:
        for c in chauffeurs:
            if (g['id'], c['id']) in x and pulp.value(x[(g['id'], c['id'])]) > 0.5:
                assignments.setdefault(g['id'], []).append({
                    "chauffeur": c['id'],
                    "trajet": "simple",
                    "combo_id": None,
                    "combiné_avec": []
                })
    
    # Log solo assignments
    solo_assignments = sum(1 for g in groupes for c in chauffeurs 
                          if (g['id'], c['id']) in x and pulp.value(x[(g['id'], c['id'])]) > 0.5)
    logger.info(f"Solo assignments found: {solo_assignments}")

    # Affectations combinées
    combo_counter = 1  # Un compteur pour créer des identifiants uniques
    for (g1_id, g2_id, c_id), var in y.items():
        if pulp.value(var) > 0.5:
            # Créer un ID unique avec timestamp
            combo_id = f"combo_{session_timestamp}_{combo_counter}"
            combo_counter += 1

            # Ajouter les informations pour le premier groupe
            assignments.setdefault(g1_id, []).append({
                "chauffeur": c_id,
                "trajet": "combiné",
                "combo_id": combo_id,
                "combiné_avec": [g2_id]  # Ce groupe est combiné avec g2
            })

            # Ajouter les informations pour le deuxième groupe
            assignments.setdefault(g2_id, []).append({
                "chauffeur": c_id,
                "trajet": "combiné",
                "combo_id": combo_id,
                "combiné_avec": [g1_id]  # Ce groupe est combiné avec g1
            })
    
    # Log combo assignments
    combo_assignments = sum(1 for (g1_id, g2_id, c_id), var in y.items() 
                           if pulp.value(var) > 0.5)
    logger.info(f"Combo assignments found: {combo_assignments}")
    
    return assignments




# =============================================================================
# Vérifier la couverture de tous les groupes et retraiter ceux non couverts
# =============================================================================
def groupes_non_couverts(assignments, groupes):
    """
    Identify uncovered groups with logging.
    """
    non_couverts = [g for g in groupes if g['id'] not in assignments or len(assignments[g['id']]) == 0]
    
    logger.warning(f"Uncovered groups found: {len(non_couverts)}")
    for group in non_couverts:
        logger.warning(f"Uncovered group ID: {group['id']}")
    
    return non_couverts


# =============================================================================
# Intégration dans le flux principal
# =============================================================================

async def solve_dispatch_problem(
    ds: PostgresDataSource, 
    date_begin: Optional[str] = None,
    date_end: Optional[str] = None,
    milp_time_limit: int = 300  # Paramètre configurable pour le timeout MILP
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Résout le problème de dispatch en utilisant d'abord MILP, puis recuit simulé si nécessaire.
    """
    start_time = time.perf_counter()
    logger.info("=== DÉBUT DU DISPATCH ===")
    logger.info(f"Paramètres - Date début: {date_begin}, Date fin: {date_end}, Timeout MILP: {milp_time_limit}s")
    
    # Configurer l'export
    FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
    if not FOLDER_ID:
        logger.error("GOOGLE_DRIVE_FOLDER_ID non trouvé dans le fichier .env Configuration Google Drive manquante")
    
    
    try:
        # 1. Récupération des données
        logger.info("Étape 1/4: Récupération des données...")
        groupes = await prepare_demandes(ds, date_begin, date_end)
        if not groupes:
            logger.info("Aucun groupe de courses valide à dispatcher. Dispatch non lancé.")
            return {}
        logger.info(f"→ {len(groupes)} groupes à traiter récupérés")
        
        chauffeurs = await prepare_chauffeurs(ds, date_begin, date_end)
        if not chauffeurs:
            logger.info("Aucun chauffeur disponible pour la période spécifiée. Dispatch non lancé.")
            return {}
        logger.info(f"→ {len(chauffeurs)} chauffeurs disponibles récupérés")

        # 2. Calcul des coûts
        logger.info("Étape 2/4: Calcul des coûts...")
        solo_cost = {}
        combo_cost = {}
        
        logger.debug("Calcul des coûts solo...")
        for g in groupes:
            if 'duree_trajet_min' not in g: continue
            for c in chauffeurs:
                try:
                    solo_cost[(g['id'],c['id'])] = travel_time_single(c,g)
                except Exception as e:
                    logger.warning(f"Erreur calcul coût solo groupe {g['id']} chauffeur {c['id']}: {str(e)}")
        
        logger.debug("Calcul des coûts combinés...")
        for g1 in groupes:
            if 't_min' not in g1: continue
            for g2 in groupes:
                if g1['id']>=g2['id'] or 't_min' not in g2: continue
                if abs(g1['t_min']-g2['t_min'])<=45:
                    for c in chauffeurs:
                        if c['n']>=(g1['ng']+g2['ng']):
                            cost = combined_route_cost(c,g1,g2)
                            if cost is not None:
                                combo_cost[(g1['id'],g2['id'],c['id'])]=cost

        logger.info(f"→ {len(solo_cost)} coûts solo et {len(combo_cost)} coûts combinés calculés")

        # 3. Résolution MILP
        logger.info("Étape 3/4: Résolution MILP...")
        logger.info(f"Lancement solveur MILP (timeout={milp_time_limit}s)")
        prob, status, x, y = solve_MILP(groupes, chauffeurs, solo_cost, combo_cost, milp_time_limit)
        assign = extract_assignments(groupes, chauffeurs, x, y)
        
        if pulp.LpStatus[status] != "Optimal":
            logger.warning(f"Statut MILP non optimal: {pulp.LpStatus[status]} - Application heuristique")
            assign = heuristic_solution(groupes, chauffeurs, solo_cost, combo_cost, assign)

        # Gestion des groupes non couverts
        nc = [g for g in groupes if g['id'] not in assign or not assign[g['id']]]
        if nc:
            logger.warning(f"{len(nc)} groupes non couverts - Tentative résolution complémentaire")
            prob2, s2, x2, y2 = solve_MILP(nc, chauffeurs, solo_cost, combo_cost, milp_time_limit)
            sub = extract_assignments(nc, chauffeurs, x2, y2)
            if pulp.LpStatus[s2] != "Optimal":
                logger.warning("Résolution complémentaire non optimale - Application heuristique")
                sub = heuristic_solution(nc, chauffeurs, solo_cost, combo_cost, assign)
            for g in nc:
                assign.setdefault(g['id'],[]).extend(sub.get(g['id'],[]))

        # 4. Fallback glouton
        logger.info("Étape 4/4: Vérification couverture complète...")
        for g in groupes:
            covered = sum(next(c for c in chauffeurs if c['id']==a['chauffeur'])['n'] for a in assign.get(g['id'],[]))
            if covered < g['ng']:
                rem = g['ng'] - covered
                logger.warning(f"Groupe {g['id']} sous-couvert ({covered}/{g['ng']}) - Application fallback glouton")
                for c in sorted(chauffeurs, key=lambda c:-c['n']):
                    if rem <= 0: break
                    if (g['id'],c['id']) in solo_cost and not(g['ng']<=4 and c['n']>4):
                        assign[g['id']].append({"chauffeur":c['id'],"trajet":"simple"})
                        rem -= c['n']
        
        
        try:
            logger.info("Génération et téléchargement des rapports from_calculation...")
            file_id_avant = await generate_and_upload_affectation_reports_from_calculation(
                groupes=groupes,
                assignments=assign,
                chauffeurs=chauffeurs,

                folder_id=FOLDER_ID
            )
        except Exception as e:
            logger.error(f"Erreur lors de la génération et du téléchargement des rapports from_calculation: {str(e)}")
            

        # 5. Sauvegarde
        logger.info("Sauvegarde des affectations...")
        await save_affectations(ds, assign)
        
        try:
            logger.info("Génération et téléchargement des rapports from_db...")
            file_id_apres = await generate_and_upload_affectation_reports_from_db(
                date_begin=date_begin,
                date_end=date_end,
                ds=ds,
                folder_id=FOLDER_ID
            )   
        except Exception as e:
            logger.error(f"Erreur lors de la génération et du téléchargement des rapports from_db: {str(e)}")
            

        duration = time.perf_counter() - start_time
        logger.info(f"=== DISPATCH TERMINÉ AVEC SUCCÈS ===")
        logger.info(f"Temps total: {duration:.2f} secondes")
        logger.info(f"Groupes traités: {len(groupes)}")
        logger.info(f"Chauffeurs utilisés: {len({a['chauffeur'] for g in assign for a in assign[g]})}")
        return assign
        
    except Exception as e:
        duration = time.perf_counter() - start_time
        logger.error(f"=== ÉCHEC DU DISPATCH ===")
        logger.error(f"Erreur après {duration:.2f} secondes")
        logger.error(f"Type erreur: {type(e).__name__}")
        logger.error(f"Détails: {str(e)}", exc_info=True)
        raise

async def save_affectations(ds: PostgresDataSource, assignments):
    """Sauvegarde les affectations dans la table chauffeurAffectation et met à jour les champs calculés"""
    try:
        # 1. Sauvegarde des affectations dans chauffeurAffectation
        chauffeur_affectation_query = """
            INSERT INTO chauffeurAffectation (
                groupe_id, chauffeur_id, statut_affectation, date_created,
                combiner_avec_groupe_id, course_combinee_id
            ) VALUES (
                %(groupe_id)s, %(chauffeur_id)s, %(statut)s, NOW(),
                %(combiner_avec_groupe_id)s, %(course_combinee_id)s
            )
            ON CONFLICT (groupe_id, chauffeur_id) DO UPDATE
            SET 
                statut_affectation = EXCLUDED.statut_affectation,
                combiner_avec_groupe_id = EXCLUDED.combiner_avec_groupe_id,
                course_combinee_id = EXCLUDED.course_combinee_id
        """

        # 2. Traitement des affectations
        for groupe_id, affectations in assignments.items():
            for affectation in affectations:
                chauffeur_id = affectation.get('chauffeur')
                if not chauffeur_id:
                    continue

                # Récupérer les informations de combinaison depuis l'objet assignments
                combiner_avec_groupe_id = None
                course_combinee_id = None
                if 'combiné_avec' in affectation and affectation['combiné_avec']:
                    combiner_avec_groupe_id = ",".join(map(str, affectation['combiné_avec']))
                if 'combo_id' in affectation:
                    course_combinee_id = affectation['combo_id']

                await ds.execute_transaction([(chauffeur_affectation_query, {
                    "groupe_id": groupe_id,
                    "chauffeur_id": chauffeur_id,
                    "statut": "draft",
                    "combiner_avec_groupe_id": combiner_avec_groupe_id,
                    "course_combinee_id": course_combinee_id
                })])

        # 3. Mise à jour des champs calculés dans chauffeurAffectation
        update_query = """
            UPDATE chauffeurAffectation ca
            SET 
                nombre_personne_prise_en_charge = (
                    SELECT cg.nombre_personne 
                    FROM courseGroupe cg 
                    WHERE cg.groupe_id = ca.groupe_id
                ),
                prenom_nom_chauffeur = (
                    SELECT ch.prenom_nom 
                    FROM chauffeur ch 
                    WHERE ch.chauffeur_id = ca.chauffeur_id
                ),
                nombre_place_chauffeur = (
                    SELECT ch.nombre_place 
                    FROM chauffeur ch 
                    WHERE ch.chauffeur_id = ca.chauffeur_id
                ),
                telephone_chauffeur = (
                    SELECT ch.telephone 
                    FROM chauffeur ch 
                    WHERE ch.chauffeur_id = ca.chauffeur_id
                ),
                partager_avec_chauffeur_json = (
                    SELECT jsonb_agg(
                        jsonb_build_object(
                            'prenom_nom', ch2.prenom_nom,
                            'telephone', ch2.telephone,
                            'nombre_place', ch2.nombre_place
                        )
                    )
                    FROM chauffeurAffectation ca2
                    JOIN chauffeur ch2 ON ca2.chauffeur_id = ch2.chauffeur_id
                    WHERE ca2.groupe_id = ca.groupe_id 
                    AND ca2.chauffeur_id != ca.chauffeur_id
                ),
                course_partagee = (
                    SELECT COUNT(*) > 1
                    FROM chauffeurAffectation ca2
                    WHERE ca2.groupe_id = ca.groupe_id
                ),
                passagers_json = (
                    SELECT jsonb_agg(
                        DISTINCT jsonb_build_object(
                            'prenom_nom', co.prenom_nom,
                            'telephone', co.telephone,
                            'num_vol', COALESCE(co.num_vol, 'N/A'),
                            'nombre_personne', co.nombre_personne,
                            'date_heure_prise_en_charge', co.date_heure_prise_en_charge,
                            'lieu_prise_en_charge', co.lieu_prise_en_charge,
                            'destination', co.destination,
                            'telephone_hebergement', co.telephone_hebergement,
                            'groupe_id', co.groupe_id
                        )
                    )
                    FROM course co
                    WHERE co.groupe_id = ca.groupe_id
                ),
                course_combinee = (
                    SELECT COUNT(c.*) > 0
                    FROM course c
                    WHERE c.groupe_id IN (
                        SELECT unnest(string_to_array(ca.combiner_avec_groupe_id::TEXT, ','))::bigint
                    )
                ),
                details_course_combinee_json = (
                    SELECT jsonb_agg(
                        jsonb_build_object(
                            'prenom_nom', c.prenom_nom,
                            'telephone', c.telephone,
                            'numero_vol', COALESCE(c.num_vol, 'N/A'),
                            'heure_prise_en_charge', c.date_heure_prise_en_charge,
                            'lieu_prise_en_charge', c.lieu_prise_en_charge,
                            'destination', c.destination,
                            'groupe_id', c.groupe_id
                        )
                    )
                    FROM course c
                    WHERE c.groupe_id IN (
                        SELECT unnest(string_to_array(ca.combiner_avec_groupe_id::TEXT, ','))::bigint
                    )
                ),
                vip = (
                    SELECT cg.vip 
                    FROM courseGroupe cg 
                    WHERE cg.groupe_id = ca.groupe_id
                ),
                prenom_nom_list = (
                    SELECT string_agg(DISTINCT co.prenom_nom, ' | ')
                    FROM course co
                    WHERE co.groupe_id = ca.groupe_id
                ),
                date_heure_prise_en_charge = (
                    SELECT cg.date_heure_prise_en_charge
                    FROM courseGroupe cg
                    WHERE cg.groupe_id = ca.groupe_id
                ),
                destination = (
                    SELECT cg.destination
                    FROM courseGroupe cg
                    WHERE cg.groupe_id = ca.groupe_id
                ),
                lieu_prise_en_charge = (
                    SELECT cg.lieu_prise_en_charge
                    FROM courseGroupe cg
                    WHERE cg.groupe_id = ca.groupe_id
                )
            WHERE ca.groupe_id = ANY(%(groupes_ids)s)
        """
        await ds.execute_transaction([(update_query, {"groupes_ids": list(assignments.keys())})])

    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde des affectations: {str(e)}")
        raise

async def verify_and_complete_coordinates(ds: PostgresDataSource):
    """Version utilisant uniquement le service de géocodage"""
    errors = []
    
    # 1. Traitement des chauffeurs
    chauffeurs = await ds.execute_query("""
        SELECT c.chauffeur_id, c.adresse, c.code_postal, c.hash_adresse, ag.latitude, ag.longitude
        FROM chauffeur c
        LEFT JOIN adresseGps ag ON c.hash_adresse = ag.hash_address
        WHERE (c.hash_adresse IS NULL OR ag.latitude IS NULL OR ag.longitude IS NULL)
       
    """)
    
    for ch in chauffeurs:
        try:
            chauffeur_id, adresse, code_postal, _, _, _ = ch
            
            # Validation de l'adresse
            if not adresse or adresse.strip() == "":
                logger.warning(f"Chauffeur {chauffeur_id} ignoré : adresse manquante")
                continue  # Passer au chauffeur suivant
            
            full_address = f"{adresse}, {code_postal}" if code_postal else adresse
            
            # Appel direct au service
            lat, lng = await geocoding_service.get_coordinates(full_address)
            if None in (lat, lng):
                raise ValueError("Échec du géocodage")
                
            hash_addr = generate_address_hash(full_address)
            
            await ds.execute_transaction([
                ("""
                INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (hash_address) DO UPDATE
                SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                """,
                (hash_addr, full_address, lat, lng))
            ])
            
            await ds.execute_query("""
                UPDATE chauffeur SET hash_adresse = %s WHERE chauffeur_id = %s
            """, [hash_addr, chauffeur_id])
            
        except HTTPException as e:
            logger.error(f"Erreur API géocodage pour chauffeur {chauffeur_id}: {e.detail}")
            errors.append(f"Chauffeur {chauffeur_id}: {e.detail}")
        except Exception as e:
            logger.error(f"Erreur traitement chauffeur {chauffeur_id}: {str(e)}")
            errors.append(f"Chauffeur {chauffeur_id}: {str(e)}")

    # 2. Traitement des courses
    courses = await ds.execute_query("""
        SELECT c.course_id, c.lieu_prise_en_charge, c.destination,
               c.hash_lieu_prise_en_charge, c.hash_destination,
               ag1.latitude, ag1.longitude, ag2.latitude, ag2.longitude
        FROM course c
        LEFT JOIN adresseGps ag1 ON c.hash_lieu_prise_en_charge = ag1.hash_address
        LEFT JOIN adresseGps ag2 ON c.hash_destination = ag2.hash_address
        WHERE c.hash_lieu_prise_en_charge IS NULL OR c.hash_destination IS NULL
           OR ag1.latitude IS NULL OR ag2.latitude IS NULL
    """)
    
    for cr in courses:
        try:
            course_id, pickup_addr, dest_addr, hash_pickup, hash_dest, _, _, _, _ = cr
            
            # Lieu de prise en charge
            if not hash_pickup:
                lat, lng = await geocoding_service.get_coordinates(pickup_addr)
                if None in (lat, lng):
                    raise ValueError("Échec géocodage lieu de prise en charge")
                    
                hash_addr = generate_address_hash(pickup_addr)
                await ds.execute_transaction([
                    ("""
                    INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (hash_address) DO UPDATE
                    SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                    """,
                    (hash_addr, pickup_addr, lat, lng))
                ])
                await ds.execute_query("""
                    UPDATE course SET hash_lieu_prise_en_charge = %s WHERE course_id = %s
                """, [hash_addr, course_id])
            
            # Destination
            if not hash_dest:
                lat, lng = await geocoding_service.get_coordinates(dest_addr)
                if None in (lat, lng):
                    raise ValueError("Échec géocodage destination")
                    
                hash_addr = generate_address_hash(dest_addr)
                await ds.execute_transaction([
                    ("""
                    INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (hash_address) DO UPDATE
                    SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                    """,
                    (hash_addr, dest_addr, lat, lng))
                ])
                await ds.execute_query("""
                    UPDATE course SET hash_destination = %s WHERE course_id = %s
                """, [hash_addr, course_id])
                
        except HTTPException as e:
            logger.error(f"Erreur API géocodage course {course_id}: {e.detail}")
            errors.append(f"Course {course_id}: {e.detail}")
        except Exception as e:
            logger.error(f"Erreur traitement course {course_id}: {str(e)}")
            errors.append(f"Course {course_id}: {str(e)}")

    if errors:
        raise ValueError(
            f"Échec sur {len(errors)} entrées lors de la complétion des coordonnées:\n"
            + "\n".join(errors)
        )

async def group_courses(ds: PostgresDataSource):
    """Groupe les courses similaires en utilisant les critères de lieu, destination et date"""
    try:
        # 1. Récupérer toutes les courses non groupées avec vérification des hashs
        courses = await ds.fetch_all("""
            SELECT 
                c.course_id,
                c.lieu_prise_en_charge,
                c.destination,
                c.date_heure_prise_en_charge,
                c.nombre_personne,
                c.vip,
                c.hash_route,
                c.groupe_id,
                c.hash_lieu_prise_en_charge,
                c.hash_destination,
                CASE 
                    WHEN ag1.hash_address IS NULL THEN false
                    ELSE true
                END as lieu_prise_en_charge_exists,
                CASE 
                    WHEN ag2.hash_address IS NULL THEN false
                    ELSE true
                END as destination_exists,
                CASE 
                    WHEN cc.hash_route IS NULL THEN false
                    ELSE true
                END as route_exists
            FROM course c
            LEFT JOIN adresseGps ag1 ON c.hash_lieu_prise_en_charge = ag1.hash_address
            LEFT JOIN adresseGps ag2 ON c.hash_destination = ag2.hash_address
            LEFT JOIN coursecalcul cc ON c.hash_route = cc.hash_route
            WHERE c.groupe_id IS NULL
            ORDER BY c.date_heure_prise_en_charge
        """)

        if not courses:
            logger.info("Aucune course à grouper")
            return

        # 2. Traiter les hashs manquants
        for course in courses:
            # Créer les hashs manquants pour les adresses
            if not course['lieu_prise_en_charge_exists']:
                hash_prise_en_charge = hashlib.md5(course['lieu_prise_en_charge'].encode()).hexdigest()
                # Obtenir les coordonnées
                pickup_coords = await geocoding_service.get_coordinates(course['lieu_prise_en_charge'])
                if pickup_coords:
                    lat, lng = pickup_coords  # Déballage du tuple
                    await ds.execute_transaction([
                        ("""
                        INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (hash_address) DO UPDATE
                        SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                        """,
                        (hash_prise_en_charge, course['lieu_prise_en_charge'], lat, lng))
                    ])
                    course['hash_lieu_prise_en_charge'] = hash_prise_en_charge

            if not course['destination_exists']:
                hash_destination = hashlib.md5(course['destination'].encode()).hexdigest()
                # Obtenir les coordonnées
                dest_coords = await geocoding_service.get_coordinates(course['destination'])
                if dest_coords:
                    lat, lng = dest_coords  # Déballage du tuple
                    await ds.execute_transaction([
                        ("""
                        INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (hash_address) DO UPDATE
                        SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                        """,
                        (hash_destination, course['destination'], lat, lng))
                    ])
                    course['hash_destination'] = hash_destination

            # Créer le hash de route si nécessaire
            if not course['route_exists'] and course['hash_lieu_prise_en_charge'] and course['hash_destination']:
                hash_route = f"{course['hash_lieu_prise_en_charge']}_{course['hash_destination']}"
                # Obtenir les détails du trajet
                route_details = await geocoding_service.get_route_details(
                    course['lieu_prise_en_charge'],
                    course['destination']
                )
                if route_details:
                    pickup_lat, pickup_lng = await geocoding_service.get_coordinates(course['lieu_prise_en_charge'])
                    dest_lat, dest_lng = await geocoding_service.get_coordinates(course['destination'])
                    
                    await ds.execute_transaction([
                        ("""
                        INSERT INTO coursecalcul (
                            hash_route, lieu_prise_en_charge, destination,
                            lieu_prise_en_charge_lat, lieu_prise_en_charge_lng,
                            destination_lat, destination_lng,
                            distance_vol_oiseau_km, distance_routiere_km,
                            duree_trajet_min, duree_trajet_secondes,
                            points_passage, points_passage_coords
                        ) VALUES (
                            %(hash_route)s, %(lieu_prise_en_charge)s, %(destination)s,
                            %(lieu_prise_en_charge_lat)s, %(lieu_prise_en_charge_lng)s,
                            %(destination_lat)s, %(destination_lng)s,
                            %(distance_vol_oiseau_km)s, %(distance_routiere_km)s,
                            %(duree_trajet_min)s, %(duree_trajet_secondes)s,
                            %(points_passage)s, %(points_passage_coords)s
                        ) ON CONFLICT (hash_route) DO UPDATE
                        SET distance_routiere_km = EXCLUDED.distance_routiere_km,
                            duree_trajet_min = EXCLUDED.duree_trajet_min,
                            duree_trajet_secondes = EXCLUDED.duree_trajet_secondes,
                            points_passage = EXCLUDED.points_passage,
                            points_passage_coords = EXCLUDED.points_passage_coords
                        """, {
                            'hash_route': hash_route,
                            'lieu_prise_en_charge': course['lieu_prise_en_charge'],
                            'destination': course['destination'],
                            'lieu_prise_en_charge_lat': pickup_lat,
                            'lieu_prise_en_charge_lng': pickup_lng,
                            'destination_lat': dest_lat,
                            'destination_lng': dest_lng,
                            'distance_vol_oiseau_km': route_details['distance_vol_oiseau_km'],
                            'distance_routiere_km': route_details['distance_routiere_km'],
                            'duree_trajet_min': route_details['duree_trajet_min'],
                            'duree_trajet_secondes': route_details['duree_trajet_secondes'],
                            'points_passage': route_details['points_passage'],
                            'points_passage_coords': route_details['points_passage_coords']
                        })])
                    course['hash_route'] = hash_route

        # 3. Créer un dictionnaire pour stocker les groupes
        groups = {}
        
        for course in courses:
            # Créer une clé unique pour le groupe basée sur les critères
            group_key = (
                course['lieu_prise_en_charge'],
                course['destination'],
                course['date_heure_prise_en_charge']
            )
            
            if group_key not in groups:
                groups[group_key] = {
                    'courses': [],
                    'total_personnes': 0,
                    'vip': False,
                    'lieu_prise_en_charge': [],
                    'destination': [],
                    'date_heure_prise_en_charge': [],
                    'hash_route': course['hash_route'],
                    'hash_lieu_prise_en_charge': course['hash_lieu_prise_en_charge'],
                    'hash_destination': course['hash_destination'],
                    'course_ids': []
                }
            
            # Ajouter les informations à la liste
            groups[group_key]['courses'].append(course)
            groups[group_key]['total_personnes'] += course['nombre_personne']
            groups[group_key]['vip'] = groups[group_key]['vip'] or course['vip']
            groups[group_key]['lieu_prise_en_charge'].append(course['lieu_prise_en_charge'])
            groups[group_key]['destination'].append(course['destination'])
            groups[group_key]['date_heure_prise_en_charge'].append(course['date_heure_prise_en_charge'])
            groups[group_key]['course_ids'].append(course['course_id'])

        # 4. Insérer les groupes dans courseGroupe et mettre à jour les courses
        for group_key, group_data in groups.items():
            # Créer les JSON arrays pour les listes
            lieu_prise_en_charge_json = json.dumps(list(set(group_data['lieu_prise_en_charge'])))
            destination_json = json.dumps(list(set(group_data['destination'])))
            date_heure_prise_en_charge_json = json.dumps(
                [dt.isoformat() for dt in sorted(set(group_data['date_heure_prise_en_charge']))]
            )

            # Insérer le groupe
            groupe_id = await ds.execute_transaction([
                ("""
                INSERT INTO courseGroupe (
                    lieu_prise_en_charge,
                    destination,
                    date_heure_prise_en_charge,
                    nombre_personne,
                    vip,
                    lieu_prise_en_charge_json,
                    destination_json,
                    date_heure_prise_en_charge_json,
                    hash_route,
                    hash_lieu_prise_en_charge,
                    hash_destination
                ) VALUES (
                    %(lieu_prise_en_charge)s,
                    %(destination)s,
                    %(date_heure_prise_en_charge)s,
                    %(nombre_personne)s,
                    %(vip)s,
                    %(lieu_prise_en_charge_json)s,
                    %(destination_json)s,
                    %(date_heure_prise_en_charge_json)s,
                    %(hash_route)s,
                    %(hash_lieu_prise_en_charge)s,
                    %(hash_destination)s
                ) RETURNING groupe_id
                """, {
                    'lieu_prise_en_charge': group_key[0],
                    'destination': group_key[1],
                    'date_heure_prise_en_charge': group_key[2],
                    'nombre_personne': group_data['total_personnes'],
                    'vip': group_data['vip'],
                    'lieu_prise_en_charge_json': lieu_prise_en_charge_json,
                    'destination_json': destination_json,
                    'date_heure_prise_en_charge_json': date_heure_prise_en_charge_json,
                    'hash_route': group_data['hash_route'],
                    'hash_lieu_prise_en_charge': group_data['hash_lieu_prise_en_charge'],
                    'hash_destination': group_data['hash_destination']
                })])

            # Mettre à jour les courses
            course_ids_str = ",".join(str(course_id) for course_id in group_data['course_ids'])
            await ds.execute_transaction([
                ("""
                UPDATE course
                SET groupe_id = %s
                WHERE course_id = ANY(STRING_TO_ARRAY(%s, ',')::bigint[])
                """, (groupe_id[0][0], course_ids_str))
            ])

        logger.info(f"Groupage terminé : {len(groups)} groupes créés ou mis à jour")

    except Exception as e:
        logger.error(f"Erreur lors du groupage des courses : {str(e)}")
        raise

async def process_course_group(processor, groupe_ids):
    """Traite un groupe de courses (mise à jour coursecalcul)"""
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
):
    """Orchestration complète du calcul des groupes et du dispatch (mise à jour coursecalcul puis solveur)"""

    ds = PostgresDataSource()
    try:
        # 1. Traiter les adresses des chauffeurs
        chauffeur_processor = ChauffeurProcessor(ds)
        await chauffeur_processor.process_chauffeur_addresses()
        
        # 2. Traiter les adresses des coursesgroupes et calculs de routes
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
        if not groupes:
            logger.info("Aucun groupe calcul de rouep à traiter Table : courseCalcul")
            

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

async def generate_and_upload_affectation_reports_from_calculation(
    groupes: List[Dict],
    assignments: Dict,
    chauffeurs: List[Dict],
    folder_id: str
) -> Tuple[str, str]:
    """
    Génère et upload deux rapports Excel (avant/après insertion) pour les affectations.
    
    Args:
        groupes: Liste des groupes à affecter
        recuit_assignments: Résultats d'affectation des chauffeurs
        chauffeurs: Liste complète des chauffeurs
        folder_id: ID du dossier Google Drive
        
    Returns:
        file_id_avant
    """
    # 1. Créer le rapport avant insertion (basé sur votre code existant)
    rows = []
    for g in groupes:
        row = {
            "group_id": g['id'],
            "N": g['ng'],
            "pickup_date": g['pickup_date'],
            "pickup_time": g['t'],
            "duree_trajet_min": g['duree_trajet_min'],
            "lieu_prise_en_charge": g.get("pickup_address", ""),
            "destination": g.get("dropoff_address", "")
        }
        aff_list = assignments.get(g['id'], [])

        for i in range(20):  # Support pour jusqu'à 20 chauffeurs
            if i < len(aff_list):
                a = aff_list[i]
                ch = next((ch for ch in chauffeurs if ch['id'] == a["chauffeur"]), {})
                row[f"chauffeur_{i+1}_id"] = ch.get('id', '')
                row[f"chauffeur_{i+1}_nom_prenom"] = ch.get('prenom_nom', '')
                row[f"chauffeur_{i+1}_trajet"] = a["trajet"]
                row[f"chauffeur_{i+1}_n"] = ch.get('n', '')
                row[f"chauffeur_{i+1}_combo_id"] = a.get("combo_id", '')
                row[f"chauffeur_{i+1}_combiné_avec"] = ','.join(map(str, a.get("combiné_avec", [])))
            else:
                row[f"chauffeur_{i+1}_id"] = ''
                row[f"chauffeur_{i+1}_nom_prenom"] = ''
                row[f"chauffeur_{i+1}_trajet"] = ''
                row[f"chauffeur_{i+1}_n"] = ''
                row[f"chauffeur_{i+1}_combo_id"] = ''
                row[f"chauffeur_{i+1}_combiné_avec"] = ''

        rows.append(row)

    df_avant = pd.DataFrame(rows)
    
    # Upload du fichier avant insertion
    file_id_avant = await save_and_upload_to_drive(
        df=df_avant,
        folder_id=folder_id,
        file_prefix="affectations_from_calculation",
        subfolder_name="affectations",
        format_excel=True,
        index=False
    )
    
    return file_id_avant


async def generate_and_upload_affectation_reports_from_db(
    date_begin: str,
    date_end: str,
    ds: PostgresDataSource,
    folder_id: str
) -> Tuple[str, str]:
    """
    Génère et upload deux rapports Excel (avant/après insertion) pour les affectations.
    
    Args:
        date_begin: Date de début de la période
        date_end: Date de fin de la période
        ds: DataSource pour requêter la base de données
        folder_id: ID du dossier Google Drive
        
    Returns:
         file_id_apres
    """
    
    # 2. Récupérer les données après insertion depuis la table chaufeuraffectation
    query = f"""
        SELECT 
            ca.*
        FROM chaufeuraffectation ca
        WHERE ca.date_prise_en_charge BETWEEN '{date_begin}' AND '{date_end}'
        ORDER BY ca.date_prise_en_charge, ca.groupe_id
    """
    affectations_db = await ds.fetch_all_dict(query)
    df_apres = pd.DataFrame(affectations_db)
    
    # Upload du fichier après insertion
    file_id_apres = await save_and_upload_to_drive(
        df=df_apres,
        folder_id=folder_id,
        file_prefix="affectations_from_db",
        subfolder_name="affectations",
        format_excel=True,
        index=False
    )
    
    return  file_id_apres
