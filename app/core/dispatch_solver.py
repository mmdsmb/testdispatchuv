

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
from app.core.utils import generate_address_hash
from decimal import Decimal  # Ensure this import exists at the top of the file
import json

# Configuration du logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='dispatch_log.txt',
    filemode='w'
)
logger = logging.getLogger(__name__)


# # =============================================================================
# # Résolution initiale par MILP avec time_limit de 5 minutes (300s)
# # =============================================================================

# milp_time_limit = 300  # 5 minutes
# prob, result_status, x, y = solve_MILP(groupes, chauffeurs, solo_cost, combo_cost, milp_time_limit)
# milp_solution_optimal = (pulp.LpStatus[result_status] == "Optimal")
# print("Statut MILP initial :", pulp.LpStatus[result_status])
# print("Valeur fonction objectif MILP initiale :", pulp.value(prob.objective))

# milp_assignments = extract_assignments(groupes, chauffeurs, x, y)

# # Si la solution MILP n'est pas optimale, lancer le recuit simulé
# if not milp_solution_optimal:
#     print("La solution MILP n'est pas optimale après 5 minutes. Lancement du recuit simulé...")
#     recuit_assignments = heuristic_solution(groupes, chauffeurs, solo_cost, combo_cost)
# else:
#     recuit_assignments = milp_assignments

# non_couverts = groupes_non_couverts(recuit_assignments, groupes)

# if non_couverts:
#     print("Certains groupes ne sont pas couverts. Traitement spécifique des groupes non couverts...")
#     # Première tentative via MILP uniquement pour les groupes non couverts
#     prob_nc, result_status_nc, x_nc, y_nc = solve_MILP(non_couverts, chauffeurs, solo_cost, combo_cost, milp_time_limit)
#     nc_milp_optimal = (pulp.LpStatus[result_status_nc] == "Optimal")
#     nc_assignments = extract_assignments(non_couverts, chauffeurs, x_nc, y_nc)
#     # Pour les groupes non couverts par le MILP, appliquer le recuit simulé
#     if not nc_milp_optimal:
#         print("La solution MILP pour les groupes non couverts n'est pas optimale. Lancement du recuit simulé pour ces groupes...")
#         nc_assignments = heuristic_solution(non_couverts, chauffeurs, solo_cost, combo_cost)
#     # Fusionner les affectations
#     for g in non_couverts:
#         recuit_assignments.setdefault(g['id'], [])
#         if g['id'] in nc_assignments:
#             recuit_assignments[g['id']].extend(nc_assignments[g['id']])
# else:
#     print("Tous les groupes sont couverts.")

# rows = []
# for g in groupes:
#     row = {
#         "group_id": g['id'],
#         "N": g['N'],
#         "pickup_date": g['pickup_date'],
#         "pickup_time": g['t'],
#         "duree_trajet_min": g['duree_trajet_min'],
#         "lieu_prise_en_charge": g.get("pickup_address", ""),
#         "destination": g.get("dropoff_address", "")
#     }
#     aff_list = recuit_assignments.get(g['id'], [])

#     for i in range(20):  # Support pour jusqu'à 20 chauffeurs
#         if i < len(aff_list):
#             a = aff_list[i]
#             ch = next((ch for ch in chauffeurs if ch['id'] == a["chauffeur"]), {})
#             row[f"chauffeur_{i+1}_id"] = ch.get('id', '')
#             row[f"chauffeur_{i+1}_nom_prenom"] = ch.get('prenom_nom', '')
#             row[f"chauffeur_{i+1}_trajet"] = a["trajet"]
#             row[f"chauffeur_{i+1}_n"] = ch.get('n', '')
#             # Ajouter les nouvelles informations de combinaison
#             row[f"chauffeur_{i+1}_combo_id"] = a.get("combo_id", '')
#             row[f"chauffeur_{i+1}_combiné_avec"] = ','.join(map(str, a.get("combiné_avec", [])))
#         else:
#             row[f"chauffeur_{i+1}_id"] = ''
#             row[f"chauffeur_{i+1}_nom_prenom"] = ''
#             row[f"chauffeur_{i+1}_trajet"] = ''
#             row[f"chauffeur_{i+1}_n"] = ''
#             row[f"chauffeur_{i+1}_combo_id"] = ''
#             row[f"chauffeur_{i+1}_combiné_avec"] = ''

#     rows.append(row)

# df_output = pd.DataFrame(rows)
# output_csv = "affectations_groupes_chauffeurs_final.csv"
# df_output.to_csv(output_csv, index=False)
# print(f"Le fichier CSV '{output_csv}' a été généré avec les noms des chauffeurs, lieu de prise en charge et destination.")
# print(df_output)



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
        coords = {
            'chauffeur': (float(chauffeur['lat_chauff']), float(chauffeur['long_chauff'])),
            'pickup': (float(groupe['lat_pickup']), float(groupe['long_pickup'])),
            'destination': (float(groupe['dest_lat']), float(groupe['dest_lng']))
        }
        
        # Validation finale
        for name, (lat, lng) in coords.items():
            if None in (lat, lng):
                raise ValueError(f"Coordonnée manquante ({name}) après géocodage")

        t1 = geodesic(coords['chauffeur'], coords['pickup']).kilometers
        t2 = float(groupe['duree_trajet_min'])  # Conversion explicite
        t3 = geodesic(coords['destination'], coords['chauffeur']).kilometers
        
        return t1 + t2 + t3
    except Exception as e:
        logger.error(f"Erreur de calcul pour {groupe['id']}: {e}")
        raise

def combined_route_cost(chauffeur, g1, g2):
    """
    Calcule le coût d'une route combinée.
    Retourne None si la route n'est pas réalisable pour des raisons spécifiques.
    """
    # Vérification des coordonnées
    if not all(is_finite_coordinate(coord) for coord in [
        chauffeur['lat_chauff'], chauffeur['long_chauff'],
        g1['lat_pickup'], g1['long_pickup'],
        g2['lat_pickup'], g2['long_pickup'],
        g1['dest_lat'], g1['dest_lng'],
        g2['dest_lat'], g2['dest_lng']
    ]):
        logger.warning(f"Coordonnées invalides pour la route combinée: chauffeur={chauffeur['id']}, g1={g1['id']}, g2={g2['id']}")
        return None

    # Vérification de la faisabilité temporelle
    if abs(g1['t_min'] - g2['t_min']) > 45:
        return None

    # Calcul des distances
    D = (chauffeur['lat_chauff'], chauffeur['long_chauff'])
    C1 = (g1['lat_pickup'], g1['long_pickup'])
    C2 = (g2['lat_pickup'], g2['long_pickup'])
    A1 = (g1['dest_lat'], g1['dest_lng'])
    A2 = (g2['dest_lat'], g2['dest_lng'])

    # Calcul des temps de trajet
    def t(p, q):
        return round(geodesic(p, q).kilometers)

    # Évaluation des 4 routes possibles
    routes = [
        (t(D, C1), t(C1, C2), t(C2, A1), t(A1, A2), t(A2, D)),
        (t(D, C1), t(C1, C2), t(C2, A2), t(A2, A1), t(A1, D)),
        (t(D, C2), t(C2, C1), t(C1, A1), t(A1, A2), t(A2, D)),
        (t(D, C2), t(C2, C1), t(C1, A2), t(A2, A1), t(A1, D))
    ]

    feasible_costs = []
    for route in routes:
        T_total = sum(route)
        # Vérification des contraintes temporelles
        if route == routes[0]:
            delay_pickup_g1 = route[0]
            delay_pickup_g2 = route[0] + route[1] - (g2['t_min'] - g1['t_min'])
            delay_arrival_g1 = (route[0] + route[1] + route[2]) - travel_time_single(chauffeur, g1)
            delay_arrival_g2 = (route[0] + route[1] + route[2] + route[3]) - travel_time_single(chauffeur, g2)
        elif route == routes[1]:
            delay_pickup_g1 = route[0]
            delay_pickup_g2 = route[0] + route[1] - (g2['t_min'] - g1['t_min'])
            delay_arrival_g2 = (route[0] + route[1] + route[2]) - travel_time_single(chauffeur, g2)
            delay_arrival_g1 = (route[0] + route[1] + route[2] + route[3]) - travel_time_single(chauffeur, g1)
        elif route == routes[2]:
            delay_pickup_g2 = route[0]
            delay_pickup_g1 = route[0] + route[1] - (g1['t_min'] - g2['t_min'])
            delay_arrival_g1 = (route[0] + route[1] + route[2]) - travel_time_single(chauffeur, g1)
            delay_arrival_g2 = (route[0] + route[1] + route[2] + route[3]) - travel_time_single(chauffeur, g2)
        else:  # Route4
            delay_pickup_g2 = route[0]
            delay_pickup_g1 = route[0] + route[1] - (g1['t_min'] - g2['t_min'])
            delay_arrival_g2 = (route[0] + route[1] + route[2]) - travel_time_single(chauffeur, g2)
            delay_arrival_g1 = (route[0] + route[1] + route[2] + route[3]) - travel_time_single(chauffeur, g1)

        if (delay_pickup_g1 <= 40 and delay_pickup_g2 <= 40
            and delay_arrival_g1 <= 60 and delay_arrival_g2 <= 60):
            feasible_costs.append(T_total)

    return min(feasible_costs) if feasible_costs else None

# =============================================================================
# Lecture et préparation des données (version PostgresDataSource)
# =============================================================================

async def prepare_demandes(ds: PostgresDataSource, date_begin: Optional[str] = None, date_end: Optional[str] = None):
    """Récupère les courses avec calcul des distances en Python (sans SQL geodesic)"""
    # query = """
    #     SELECT 
    #         c.course_id as id,
    #         c.nombre_personne as ng,
    #         c.lieu_prise_en_charge as pickup_address,
    #         c.destination as dropoff_address,
    #         ag_pickup.latitude as lat_pickup,
    #         ag_pickup.longitude as long_pickup,
    #         ag_dest.latitude as dest_lat,
    #         ag_dest.longitude as dest_lng,
    #         c.date_heure_prise_en_charge,
    #         EXTRACT(EPOCH FROM (c.date_heure_prise_en_charge - NOW()))/60 as t_min,
    #         cc.duree_trajet_min
    #     FROM course c
    #     JOIN adresseGps ag_pickup ON c.hash_lieu_prise_en_charge = ag_pickup.hash_address
    #     JOIN adresseGps ag_dest ON c.hash_destination = ag_dest.hash_address
    #     LEFT JOIN coursecalcul cc ON c.hash_route = cc.hash_route
    # """
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
        raise ValueError("Aucune course valide après vérification des coordonnées")
    
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
        prob = pulp.LpProblem("Affectation_Chauffeurs_Groupes", pulp.LpMinimize)

        # Variables d'affectation solo
        x = {}
        for g in groupes:
            for c in chauffeurs:
                if (g['id'], c['id']) in solo_cost:
                    x[(g['id'], c['id'])] = pulp.LpVariable(f"x_{g['id']}_{c['id']}", 0, 1, pulp.LpBinary)

        # Variables d'affectation combinée
        y = {}
        for key, cost in combo_cost.items():
            g1_id, g2_id, c_id = key
            y[key] = pulp.LpVariable(f"y_{g1_id}_{g2_id}_{c_id}", 0, 1, pulp.LpBinary)

        # Fonction objectif : Minimiser le temps total des trajets
        objective = []
        for key, var in x.items():
            objective.append(solo_cost[key] * var)
        for key, var in y.items():
            objective.append(combo_cost[key] * var)
        prob += pulp.lpSum(objective), "Temps_Total"

        # Contrainte de couverture : chaque groupe doit être pris en charge entièrement
        chauffeur_capacity = {ch['id']: ch['n'] for ch in chauffeurs}
        for g in groupes:
            solo_cap = pulp.lpSum(c['n'] * x[(g['id'], c['id'])] for c in chauffeurs if (g['id'], c['id']) in x)
            comb_cap = pulp.lpSum(0.5 * chauffeur_capacity[c_id] * var
                                for (g1_id, g2_id, c_id), var in y.items() if g['id'] in [g1_id, g2_id])
            prob += solo_cap + comb_cap >= g['ng'], f"Couverture_{g['id']}"

        # Contrainte de minimalité des affectations multiples
        M_big = 1e4
        z = {}
        constraint_counter = 0  # Compteur pour les noms de contraintes uniques
        
        for g in groupes:
            for c in chauffeurs:
                z[(g['id'], c['id'])] = pulp.LpVariable(f"z_{g['id']}_{c['id']}", 0, 1, pulp.LpBinary)

        for g in groupes:
            for c in chauffeurs:
                lhs = x[(g['id'], c['id'])] if (g['id'], c['id']) in x else 0
                y_sum = pulp.lpSum(var for key, var in y.items() if key[2] == c['id'] and (key[0] == g['id'] or key[1] == g['id']))
                
                # Utilisation du compteur pour rendre les noms uniques
                constraint_counter += 1
                prob += z[(g['id'], c['id'])] >= lhs, f"Lien_z_x_{g['id']}_{c['id']}_{constraint_counter}"
                
                constraint_counter += 1
                prob += z[(g['id'], c['id'])] >= y_sum, f"Lien_z_y_{g['id']}_{c['id']}_{constraint_counter}"
                
                constraint_counter += 1
                prob += z[(g['id'], c['id'])] <= lhs + y_sum, f"Lien_z_up_{g['id']}_{c['id']}_{constraint_counter}"

                expr = []
                for k in chauffeurs:
                    if k['id'] != c['id'] and (g['id'], k['id']) in x:
                        term_solo = k['n'] * x[(g['id'], k['id'])]
                        term_combo = k['n'] * pulp.lpSum(var for key, var in y.items()
                                                        if key[2] == k['id'] and (key[0] == g['id'] or key[1] == g['id']))
                        expr.append(term_solo + term_combo)
                
                constraint_counter += 1
                prob += pulp.lpSum(expr) <= g['ng'] - 1 + M_big * (1 - z[(g['id'], c['id'])]), f"Minimalite_{g['id']}_{c['id']}_{constraint_counter}"

        # Contrainte de non-chevauchement et limite des missions par chauffeur
        for c in chauffeurs:
            candidate_list = []
            for g in groupes:
                if (g['id'], c['id']) in x:
                    T_start = g['t_min']
                    t_single = solo_cost[(g['id'], c['id'])]
                    T_finish = T_start + Decimal(str(t_single))  # Convert t_single to Decimal
                    candidate_list.append((("solo", g['id'], c['id']), T_start, T_finish, x[(g['id'], c['id'])]))
            for key, var in y.items():
                if key[2] == c['id']:
                    g1 = next(g for g in groupes if g['id'] == key[0])
                    g2 = next(g for g in groupes if g['id'] == key[1])
                    T_start = min(g1['t_min'], g2['t_min'])
                    t_combo = combo_cost.get(key, None)
                    if t_combo is not None:
                        T_finish = T_start + t_combo
                        candidate_list.append((("combo", key[0], key[1], c['id']), T_start, T_finish, var))
            for i in range(len(candidate_list)):
                for j in range(i+1, len(candidate_list)):
                    _, Tsi, Tfi, var_i = candidate_list[i]
                    _, Tsj, Tfj, var_j = candidate_list[j]
                    if Tsi < Tfj and Tsj < Tfi:
                        constraint_counter += 1
                        prob += var_i + var_j <= 1, f"NonChevauchement_{c['id']}_{i}_{j}_{constraint_counter}"
            
            solo_vars = [x[(g['id'], c['id'])] for g in groupes if (g['id'], c['id']) in x]
            combo_vars = [var for key, var in y.items() if key[2] == c['id']]
            constraint_counter += 1
            prob += pulp.lpSum(solo_vars + combo_vars) <= 4, f"MaxMissions_{c['id']}_{constraint_counter}"

        # Contrainte supplémentaire sur la capacité pour groupes de faible demande
        for g in groupes:
            if g['ng'] <= 4:
                for c in chauffeurs:
                    if c['n'] > 4 and (g['id'], c['id']) in x:
                        constraint_counter += 1
                        prob += x[(g['id'], c['id'])] == 0, f"Capacite_minimale_solo_{g['id']}_{c['id']}_{constraint_counter}"

        for key, var in y.items():
            g1 = next(g for g in groupes if g['id'] == key[0])
            g2 = next(g for g in groupes if g['id'] == key[1])
            c  = next(ch for ch in chauffeurs if ch['id'] == key[2])
            if (g1['ng'] <= 3 or g2['ng'] <= 3) and c['n'] > 4:
                constraint_counter += 1
                prob += var == 0, f"Capacite_minimale_combo_{key[0]}_{key[1]}_{key[2]}_{constraint_counter}"

        solver = pulp.PULP_CBC_CMD(timeLimit=time_limit, msg=True)
        result_status = prob.solve(solver)
        
        logger.info(f"Statut de la résolution MILP : {pulp.LpStatus[result_status]}")
        logger.info(f"Valeur de la fonction objectif : {pulp.value(prob.objective)}")
        
        return prob, result_status, x, y
    
    except Exception as e:
        logger.error(f"Erreur lors de la résolution MILP : {e}")
        raise

# =============================================================================
# Méthode heuristique par recuit simulé
# =============================================================================
def heuristic_solution(groupes, chauffeurs, solo_cost, combo_cost, existing_assignments=None):
    """
    Recuit simulé pour générer une solution admissible.
    Pour simplifier, ici on construit initialement des affectations solo (en respectant non-chevauchement et max 4 missions)
    puis on applique un recuit sur l'ensemble des groupes (ou uniquement sur ceux non couverts si existing_assignments est fourni).
    """
    
    logger.info("Début de la solution heuristique par recuit simulé")
    logger.info(f"Nombre de groupes à traiter : {len(groupes)}")
    logger.info(f"Nombre de chauffeurs disponibles : {len(chauffeurs)}")
    
    start_time = time.time()
    solution = None
    
    try:
        # Si existing_assignments est fourni, ne traiter que les groupes non couverts
        if existing_assignments is None:
            groups_to_process = groupes
        else:
            groups_to_process = [g for g in groupes if g['id'] not in existing_assignments or len(existing_assignments[g['id']]) == 0]
        assignments = {} if existing_assignments is None else existing_assignments.copy()
        driver_schedule = {c['id']: [] for c in chauffeurs}
        driver_missions_count = {c['id']: 0 for c in chauffeurs}

        # Construction d'une solution initiale gloutonne pour les groupes à traiter
        sorted_groups = sorted(groups_to_process, key=lambda g: g['t_min'])
        for g in sorted_groups:
            feasible_assignments = []
            for c in chauffeurs:
                cost = solo_cost.get((g['id'], c['id']))
                if cost is not None and driver_missions_count[c['id']] < 4:
                    logger.debug(f"Type de start_time: {type(g['t_min'])}, valeur: {g['t_min']}")
                    logger.debug(f"Type de cost: {type(cost)}, valeur: {cost}")
                    start_time = float(g['t_min'])  # Conversion explicite en float
                    finish_time = start_time + float(cost)  # Conversion explicite en float
                    overlap = False
                    for (s, f) in driver_schedule[c['id']]:
                        if not (finish_time <= s or start_time >= f):
                            overlap = True
                            break
                    if not overlap:
                        feasible_assignments.append((c['id'], cost, start_time, finish_time))
            if feasible_assignments:
                chosen = min(feasible_assignments, key=lambda x: x[1])
                c_id, cost, start_time, finish_time = chosen
                assignments.setdefault(g['id'], []).append({"chauffeur": c_id, "trajet": "simple"})
                driver_schedule[c_id].append((start_time, finish_time))
                driver_missions_count[c_id] += 1
            else:
                assignments.setdefault(g['id'], [])

        # Fonction objectif simple (somme des coûts)
        def objective(sol):
            total = 0
            for g in groupes:
                if sol.get(g['id']):
                    for assign in sol[g['id']]:
                        c_id = assign['chauffeur']
                        total += solo_cost.get((g['id'], c_id), 0)
            return total

        current_solution = assignments
        current_obj = objective(current_solution)
        best_solution = current_solution
        best_obj = current_obj

        T = 100.0
        T_min = 1e-3
        alpha = 0.995
        max_time = 10 * 60  # 10 minutes
        start_time_sim = time.time()

        # Perturbation : pour un groupe choisi aléatoirement, tenter de changer d'affectation
        def perturb(sol):
            new_sol = {g_id: list(assigns) for g_id, assigns in sol.items()}
            g = random.choice(groups_to_process)
            feasible = []
            for c in chauffeurs:
                cost = solo_cost.get((g['id'], c['id']))
                if cost is not None:
                    feasible.append((c['id'], cost))
            if feasible:
                new_c = random.choice(feasible)
                new_sol[g['id']] = [{"chauffeur": new_c[0], "trajet": "simple"}]
            return new_sol

        while T > T_min and (time.time() - start_time_sim) < max_time:
            new_solution = perturb(current_solution)
            new_obj = objective(new_solution)
            delta = new_obj - current_obj
            if delta < 0 or random.random() < math.exp(-delta / T):
                current_solution = new_solution
                current_obj = new_obj
                if new_obj < best_obj:
                    best_solution = new_solution
                    best_obj = new_obj
            T *= alpha

        print("Solution heuristique obtenue avec coût total approximatif :", best_obj)
        
        
        solution = best_solution
        
        end_time = time.time()
        logger.info(f"Fin du recuit simulé")
        logger.info(f"Temps d'exécution : {end_time - start_time:.2f} secondes")
        logger.info(f"Coût total de la solution heuristique : {best_obj}")
        
        return solution
    
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution du recuit simulé : {e}")
        raise


def extract_assignments(groupes, chauffeurs, x, y):
    logger.info("Extracting group-driver assignments")
    assignments = {}
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
            # Créer un ID unique pour cette combinaison
            combo_id = f"combo_{combo_counter}"
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
    logger.info("Démarrage du dispatch...")
    
    try:
        # 1. Récupération des données
        groupes = await prepare_demandes(ds, date_begin, date_end)
        logger.info(f"Nombre de groupes à traiter : {len(groupes)}")

        #print("groupes" , groupes)
        
        chauffeurs = await prepare_chauffeurs(ds, date_begin, date_end)
        logger.info(f"Nombre de chauffeurs disponibles : {len(chauffeurs)}")

        #print("chauffeurs" , chauffeurs)

        # 2. Calcul des coûts
        logger.debug("Calcul des coûts...")
        solo_cost = {
            (g['id'], c['id']): travel_time_single(c, g)
            for g in groupes
            for c in chauffeurs
        }
        
        combo_cost = {}
        for g1 in groupes:
            for g2 in groupes:
                if g1['id'] < g2['id']:  # Évite les doublons
                    for c in chauffeurs:
                        cost = combined_route_cost(c, g1, g2)
                        if cost is not None:  # Ne garde que les routes réalisables
                            combo_cost[(g1['id'], g2['id'], c['id'])] = cost

        # Vérification qu'il y a des routes réalisables
        if not combo_cost:
            logger.warning("Aucune route combinée réalisable trouvée")
            return []

        # Vérification qu'il y a assez de routes pour le MILP
        if len(combo_cost) < len(groupes) * len(chauffeurs):
            logger.warning(f"Nombre limité de routes combinées réalisables: {len(combo_cost)}")

        # 3. Résolution MILP initiale
        logger.info(f"Lancement MILP (timeout={milp_time_limit}s)")
        prob, status, x, y = solve_MILP(groupes, chauffeurs, solo_cost, combo_cost, milp_time_limit)
        milp_optimal = (pulp.LpStatus[status] == "Optimal")
       
        
        if milp_optimal:
            assignments = extract_assignments(groupes, chauffeurs, x, y)
            logger.info("Solution MILP optimale trouvée")
        else:
            logger.warning("Solution MILP non optimale, lancement recuit simulé")
            assignments = heuristic_solution(groupes, chauffeurs, solo_cost, combo_cost)

        # 4. Traitement des groupes non couverts
        non_couverts = groupes_non_couverts(assignments, groupes)
        if non_couverts:
            logger.warning(f"{len(non_couverts)} groupes non couverts, retraitement")
            prob_nc, status_nc, x_nc, y_nc = solve_MILP(non_couverts, chauffeurs, solo_cost, combo_cost, milp_time_limit)
            
            milp_optimal_nc = (pulp.LpStatus[status_nc] == "Optimal")
            
            logger.info(f"Solution MILP  , retraitement GROUPES NON COUVERTS : {milp_optimal_nc}")
            if milp_optimal_nc:
                nc_assignments = extract_assignments(non_couverts, chauffeurs, x_nc, y_nc)
            else:
                nc_assignments = heuristic_solution(non_couverts, chauffeurs, solo_cost, combo_cost)
            
            # Fusion des affectations
            for g in non_couverts:
                assignments.setdefault(g['id'], []).extend(nc_assignments.get(g['id'], []))

        # 5. Sauvegarde des affectations
        logger.info("Sauvegarde des affectations...")
        await save_affectations(ds, assignments)

        duration = time.perf_counter() - start_time
        logger.info(f"Dispatch terminé en {duration:.2f} secondes")
        return assignments
        
    except Exception as e:
        logger.error(f"Échec après {time.perf_counter() - start_time:.2f} secondes", exc_info=True)
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
            
            await ds.execute_transaction([(
                """
                INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (hash_address) DO UPDATE
                SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                """,
                (hash_addr, full_address, lat, lng)
            )])
            
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
                await ds.execute_transaction([(
                    """
                    INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (hash_address) DO UPDATE
                    SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                    """,
                    (hash_addr, pickup_addr, lat, lng)
                )])
                await ds.execute_query("""
                    UPDATE course SET hash_lieu_prise_en_charge = %s WHERE course_id = %s
                """, [hash_addr, course_id])
            
            # Destination
            if not hash_dest:
                lat, lng = await geocoding_service.get_coordinates(dest_addr)
                if None in (lat, lng):
                    raise ValueError("Échec géocodage destination")
                    
                hash_addr = generate_address_hash(dest_addr)
                await ds.execute_transaction([(
                    """
                    INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (hash_address) DO UPDATE
                    SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                    """,
                    (hash_addr, dest_addr, lat, lng)
                )])
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
                    await ds.execute_transaction([("""
                        INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (hash_address) DO UPDATE
                        SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                    """, (hash_prise_en_charge, course['lieu_prise_en_charge'], lat, lng))])
                    course['hash_lieu_prise_en_charge'] = hash_prise_en_charge

            if not course['destination_exists']:
                hash_destination = hashlib.md5(course['destination'].encode()).hexdigest()
                # Obtenir les coordonnées
                dest_coords = await geocoding_service.get_coordinates(course['destination'])
                if dest_coords:
                    lat, lng = dest_coords  # Déballage du tuple
                    await ds.execute_transaction([("""
                        INSERT INTO adresseGps (hash_address, address, latitude, longitude)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (hash_address) DO UPDATE
                        SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                    """, (hash_destination, course['destination'], lat, lng))])
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
                    
                    await ds.execute_transaction([("""
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
            groupe_id = await ds.execute_transaction([("""
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
            await ds.execute_transaction([("""
                UPDATE course
                SET groupe_id = %s
                WHERE course_id = ANY(STRING_TO_ARRAY(%s, ',')::bigint[])
            """, (groupe_id[0][0], course_ids_str))])

        logger.info(f"Groupage terminé : {len(groups)} groupes créés ou mis à jour")

    except Exception as e:
        logger.error(f"Erreur lors du groupage des courses : {str(e)}")
        raise
