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

async def geocode_address(address: str):
    """Version moderne avec httpx"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1}
        )
        response.raise_for_status()
        data = response.json()
        if data:
            return f"{data[0]['lat']},{data[0]['lon']}"
    return None

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
    """
    Calcule le temps total (en minutes) pour un service solo :
    domicile -> pickup -> destination -> retour domicile.
    On suppose ici que 1 km ≈ 1 minute.
    """
    logger.info(f"Calcul du temps de trajet pour le chauffeur {chauffeur['id']} et le groupe {groupe['id']}")
    try:
        if not is_finite_coordinate(chauffeur['lat_chauff'], chauffeur['long_chauff'],
                                    groupe['lat_pickup'], groupe['long_pickup'],
                                    groupe['dest_lat'], groupe['dest_lng']):
            logger.error(f"Coordonnées invalides pour chauffeur {chauffeur['id']} ou groupe {groupe['id']}")
            raise ValueError(f"Coordonnées invalides pour chauffeur {chauffeur['id']} ou groupe {groupe['id']}")
        
        t1 = round(geodesic((chauffeur['lat_chauff'], chauffeur['long_chauff']),
                            (groupe['lat_pickup'], groupe['long_pickup'])).kilometers)
        t2 = round(groupe['duree_trajet_min'])
        t3 = round(geodesic((groupe['dest_lat'], groupe['dest_lng']),
                            (chauffeur['lat_chauff'], chauffeur['long_chauff'])).kilometers)
        
        total_time = t1 + t2 + t3
        logger.info(f"Temps de trajet calculé : {total_time} minutes (t1: {t1}, t2: {t2}, t3: {t3})")
        return total_time
    except Exception as e:
        logger.error(f"Erreur lors du calcul du temps de trajet : {e}")
        raise

def combined_route_cost(chauffeur, g1, g2):
    """
    Calcule, pour un chauffeur et deux groupes g1 et g2,
    le coût minimal (temps total en minutes) parmi 4 itinéraires possibles,
    en respectant les contraintes de délais de pickup et d'arrivée.
    Renvoie None si aucune route n'est admissible.
    """
    logger.info(f"Calcul du coût de route combinée pour chauffeur {chauffeur['id']}, groupes {g1['id']} et {g2['id']}")
    
    if abs(g1['t_min'] - g2['t_min']) > 45:
        return None

    D = (chauffeur['lat_chauff'], chauffeur['long_chauff'])
    C1 = (g1['lat_pickup'], g1['long_pickup'])
    C2 = (g2['lat_pickup'], g2['long_pickup'])
    A1 = (g1['dest_lat'], g1['dest_lng'])
    A2 = (g2['dest_lat'], g2['dest_lng'])

    Tsolo1 = travel_time_single(chauffeur, g1)
    Tsolo2 = travel_time_single(chauffeur, g2)

    # Fonction de calcul de distance arrondie
    def t(p, q):
        return round(geodesic(p, q).kilometers)

    feasible_costs = []

    # On évalue les 4 routes possibles
    routes = [
        (t(D, C1), t(C1, C2), t(C2, A1), t(A1, A2), t(A2, D)), # Route1
        (t(D, C1), t(C1, C2), t(C2, A2), t(A2, A1), t(A1, D)), # Route2
        (t(D, C2), t(C2, C1), t(C1, A1), t(A1, A2), t(A2, D)), # Route3
        (t(D, C2), t(C2, C1), t(C1, A2), t(A2, A1), t(A1, D))  # Route4
    ]
    for route in routes:
        T_total = sum(route)
        # Estimation des délais en se basant sur l'ordre des pickups et des arrivées
        if route == routes[0]:
            delay_pickup_g1 = route[0]
            delay_pickup_g2 = route[0] + route[1] - (g2['t_min'] - g1['t_min'])
            delay_arrival_g1 = (route[0] + route[1] + route[2]) - Tsolo1
            delay_arrival_g2 = (route[0] + route[1] + route[2] + route[3]) - Tsolo2
        elif route == routes[1]:
            delay_pickup_g1 = route[0]
            delay_pickup_g2 = route[0] + route[1] - (g2['t_min'] - g1['t_min'])
            delay_arrival_g2 = (route[0] + route[1] + route[2]) - Tsolo2
            delay_arrival_g1 = (route[0] + route[1] + route[2] + route[3]) - Tsolo1
        elif route == routes[2]:
            delay_pickup_g2 = route[0]
            delay_pickup_g1 = route[0] + route[1] - (g1['t_min'] - g2['t_min'])
            delay_arrival_g1 = (route[0] + route[1] + route[2]) - Tsolo1
            delay_arrival_g2 = (route[0] + route[1] + route[2] + route[3]) - Tsolo2
        else:  # Route4
            delay_pickup_g2 = route[0]
            delay_pickup_g1 = route[0] + route[1] - (g1['t_min'] - g2['t_min'])
            delay_arrival_g2 = (route[0] + route[1] + route[2]) - Tsolo2
            delay_arrival_g1 = (route[0] + route[1] + route[2] + route[3]) - Tsolo1

        if (delay_pickup_g1 <= 40 and delay_pickup_g2 <= 40
            and delay_arrival_g1 <= 60 and delay_arrival_g2 <= 60):
            feasible_costs.append(T_total)

    result = min(feasible_costs) if feasible_costs else None
    
    if result is not None:
        logger.info(f"Coût de route combinée trouvé : {result} minutes")
    else:
        logger.warning(f"Aucune route combinée admissible pour chauffeur {chauffeur['id']}, groupes {g1['id']} et {g2['id']}")
    
    return result

# =============================================================================
# Lecture et préparation des données (version PostgresDataSource)
# =============================================================================

async def prepare_demandes(ds: PostgresDataSource, date=None):
    """Récupère et prépare les demandes de courses"""
    # Requête de base
    query = """
        SELECT 
            c.course_id as id,
            c.nombre_personne as n,
            c.lieu_prise_en_charge as pickup_address,
            c.destination as dropoff_address,
            ag_pickup.latitude as lat_pickup,
            ag_pickup.longitude as long_pickup,
            ag_dest.latitude as dest_lat,
            ag_dest.longitude as dest_lng,
            c.date_heure_prise_en_charge,
            EXTRACT(EPOCH FROM (c.date_heure_prise_en_charge - NOW()))/60 as t_min
        FROM course c
        LEFT JOIN adresseGps ag_pickup ON c.hash_lieu_prise_en_charge = ag_pickup.hash_address
        LEFT JOIN adresseGps ag_dest ON c.hash_destination = ag_dest.hash_address
    """
    
    params = {}
    if date:
        query += " WHERE DATE(c.date_heure_prise_en_charge) = %(date)s"
        params["date"] = date
    
    rows = await ds.fetch_all(query, params)
    
    # Conversion en DataFrame et préparation (similaire à la logique Excel)
    df = pd.DataFrame(rows)
    df['date_heure_prise_en_charge'] = pd.to_datetime(df['date_heure_prise_en_charge'])
    df['pickup_date'] = df['date_heure_prise_en_charge'].dt.strftime("%Y-%m-%d")
    df['t'] = df['date_heure_prise_en_charge'].dt.strftime("%H:%M")
    df['duree_trajet_min'] = 15  # Valeur par défaut, à adapter selon votre logique
    
    return df[['id', 'n', 'pickup_date', 't', 't_min', 'lat_pickup', 'long_pickup', 
               'dest_lat', 'dest_lng', 'duree_trajet_min', 'pickup_address', 'dropoff_address']]

async def prepare_chauffeurs(ds: PostgresDataSource):
    """Récupère et prépare les chauffeurs disponibles"""
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
        AND dc.date_debut <= NOW() 
        AND dc.date_fin >= NOW()
    """
    
    rows = await ds.fetch_all(query)
    df = pd.DataFrame(rows)

    # Debug: Afficher les colonnes disponibles
    print("Colonnes disponibles:", df.columns.tolist()) 
    
    # Conversion des types si nécessaire
    df['lat_chauff'] = pd.to_numeric(df['lat_chauff'], errors='coerce')
    df['long_chauff'] = pd.to_numeric(df['long_chauff'], errors='coerce')
    
    return df[['id', 'n', 'lat_chauff', 'long_chauff', 'availability_date', 'prenom_nom']]

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
            prob += solo_cap + comb_cap >= g['N'], f"Couverture_{g['id']}"

        # Contrainte de minimalité des affectations multiples
        M_big = 1e4
        z = {}
        for g in groupes:
            for c in chauffeurs:
                z[(g['id'], c['id'])] = pulp.LpVariable(f"z_{g['id']}_{c['id']}", 0, 1, pulp.LpBinary)

        for g in groupes:
            for c in chauffeurs:
                lhs = x[(g['id'], c['id'])] if (g['id'], c['id']) in x else 0
                y_sum = pulp.lpSum(var for key, var in y.items() if key[2] == c['id'] and (key[0] == g['id'] or key[1] == g['id']))
                prob += z[(g['id'], c['id'])] >= lhs, f"Lien_z_x_{g['id']}_{c['id']}"
                prob += z[(g['id'], c['id'])] >= y_sum, f"Lien_z_y_{g['id']}_{c['id']}"
                prob += z[(g['id'], c['id'])] <= lhs + y_sum, f"Lien_z_up_{g['id']}_{c['id']}"

                expr = []
                for k in chauffeurs:
                    if k['id'] != c['id'] and (g['id'], k['id']) in x:
                        term_solo = k['n'] * x[(g['id'], k['id'])]
                        term_combo = k['n'] * pulp.lpSum(var for key, var in y.items()
                                                        if key[2] == k['id'] and (key[0] == g['id'] or key[1] == g['id']))
                        expr.append(term_solo + term_combo)
                prob += pulp.lpSum(expr) <= g['N'] - 1 + M_big * (1 - z[(g['id'], c['id'])]), f"Minimalite_{g['id']}_{c['id']}"

        # Contrainte de non-chevauchement et limite des missions par chauffeur
        for c in chauffeurs:
            candidate_list = []
            for g in groupes:
                if (g['id'], c['id']) in x:
                    T_start = g['t_min']
                    t_single = solo_cost[(g['id'], c['id'])]
                    T_finish = T_start + t_single
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
                        prob += var_i + var_j <= 1, f"NonChevauchement_{c['id']}_{i}_{j}"
            solo_vars = [x[(g['id'], c['id'])] for g in groupes if (g['id'], c['id']) in x]
            combo_vars = [var for key, var in y.items() if key[2] == c['id']]
            prob += pulp.lpSum(solo_vars + combo_vars) <= 4, f"MaxMissions_{c['id']}"

        # Contrainte supplémentaire sur la capacité pour groupes de faible demande
        for g in groupes:
            if g['N'] <= 4:
                for c in chauffeurs:
                    if c['n'] > 4 and (g['id'], c['id']) in x:
                        prob += x[(g['id'], c['id'])] == 0, f"Capacite_minimale_solo_{g['id']}_{c['id']}"

        for key, var in y.items():
            g1 = next(g for g in groupes if g['id'] == key[0])
            g2 = next(g for g in groupes if g['id'] == key[1])
            c  = next(ch for ch in chauffeurs if ch['id'] == key[2])
            if (g1['N'] <= 3 or g2['N'] <= 3) and c['n'] > 4:
                prob += var == 0, f"Capacite_minimale_combo_{key[0]}_{key[1]}_{key[2]}"

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
                    start_time = g['t_min']
                    finish_time = start_time + cost
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

async def solve_dispatch_problem(ds: PostgresDataSource, date_param=None):
    """Fonction principale pour résoudre le problème de dispatch"""
    # Récupération des données
    df_demandes = await prepare_demandes(ds, date_param)
    df_chauffeurs = await prepare_chauffeurs(ds)
    
    # Conversion en listes de dictionnaires
    groupes = df_demandes.to_dict(orient='records')
    chauffeurs = df_chauffeurs.to_dict(orient='records')

    # Calculate solo_cost and combo_cost
    solo_cost = {(g['id'], c['id']): travel_time_single(c, g)
                 for g in groupes for c in chauffeurs}
    combo_cost = {}
    for g1, g2 in combinations(groupes, 2):
        if abs(g1['t_min'] - g2['t_min']) <= 45:
            for c in chauffeurs:
                if c['n'] >= (g1['N'] + g2['N']):
                    cost = combined_route_cost(c, g1, g2)
                    if cost is not None:
                        combo_cost[(g1['id'], g2['id'], c['id'])] = cost

    # Move the MILP logic here
    milp_time_limit = 300  # 5 minutes
    prob, result_status, x, y = solve_MILP(groupes, chauffeurs, solo_cost, combo_cost, milp_time_limit)
    milp_solution_optimal = (pulp.LpStatus[result_status] == "Optimal")
    print("Statut MILP initial :", pulp.LpStatus[result_status])
    
    # Extract assignments
    milp_assignments = extract_assignments(groupes, chauffeurs, x, y)

    # If MILP is not optimal, use heuristic
    if not milp_solution_optimal:
        print("La solution MILP n'est pas optimale après 5 minutes. Lancement du recuit simulé...")
        recuit_assignments = heuristic_solution(groupes, chauffeurs, solo_cost, combo_cost)
    else:
        recuit_assignments = milp_assignments

    # Check for uncovered groups
    non_couverts = groupes_non_couverts(recuit_assignments, groupes)
    if non_couverts:
        print("Certains groupes ne sont pas couverts. Traitement spécifique des groupes non couverts...")
        # First try MILP for uncovered groups
        prob_nc, result_status_nc, x_nc, y_nc = solve_MILP(non_couverts, chauffeurs, solo_cost, combo_cost, milp_time_limit)
        nc_milp_optimal = (pulp.LpStatus[result_status_nc] == "Optimal")
        nc_assignments = extract_assignments(non_couverts, chauffeurs, x_nc, y_nc)
        # If MILP fails, use heuristic
        if not nc_milp_optimal:
            print("La solution MILP pour les groupes non couverts n'est pas optimale. Lancement du recuit simulé pour ces groupes...")
            nc_assignments = heuristic_solution(non_couverts, chauffeurs, solo_cost, combo_cost)
        # Merge assignments
        for g in non_couverts:
            recuit_assignments.setdefault(g['id'], [])
            if g['id'] in nc_assignments:
                recuit_assignments[g['id']].extend(nc_assignments[g['id']])

    # Generate output CSV
    rows = []
    for g in groupes:
        row = {
            "group_id": g['id'],
            "N": g['N'],
            "pickup_date": g['pickup_date'],
            "pickup_time": g['t'],
            "duree_trajet_min": g['duree_trajet_min'],
            "lieu_prise_en_charge": g.get("pickup_address", ""),
            "destination": g.get("dropoff_address", "")
        }
        aff_list = recuit_assignments.get(g['id'], [])
        for i in range(20):  # Support for up to 20 drivers
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

    df_output = pd.DataFrame(rows)
    output_csv = "affectations_groupes_chauffeurs_final.csv"
    df_output.to_csv(output_csv, index=False)
    print(f"Le fichier CSV '{output_csv}' a été généré avec les noms des chauffeurs, lieu de prise en charge et destination.")
    print(df_output)

    # Save assignments to database
    await save_affectations(ds, recuit_assignments)

async def save_affectations(ds: PostgresDataSource, affectations):
    """Sauvegarde les affectations dans la base de données"""
    query = """
        INSERT INTO chauffeurAffectation (
            groupe_id, chauffeur_id, statut_affectation, 
            date_created, date_accepted, date_done
        ) VALUES (
            %(groupe_id)s, %(chauffeur_id)s, %(statut)s,
            NOW(), NULL, NULL
        )
        ON CONFLICT (groupe_id, chauffeur_id) DO UPDATE
        SET statut_affectation = EXCLUDED.statut_affectation
    """
    
    for affectation in affectations:
        await ds.execute_transaction(query, {
            "groupe_id": affectation["groupe_id"],
            "chauffeur_id": affectation["chauffeur_id"],
            "statut": affectation["statut"]
        })