import pandas as pd
import json
from sklearn.cluster import DBSCAN
import numpy as np
from collections import defaultdict
from datetime import datetime

class RouteAnalyzer:
    def __init__(self, time_window_minutes=30, similarity_threshold=0.01, num_points=3, clustering_eps=0.01):
        """
        Initialise l'analyseur de routes avec des paramètres configurables
        """
        self.time_window_minutes = time_window_minutes
        self.similarity_threshold = similarity_threshold
        self.num_points = num_points
        self.clustering_eps = clustering_eps

    def create_time_windows(self, df, datetime_column):
        """
        Crée des fenêtres temporelles et ajoute une nouvelle colonne 'date_time_window'
        """
        df[datetime_column] = pd.to_datetime(df[datetime_column])
        df['date_time_window'] = df[datetime_column].dt.floor(f'{self.time_window_minutes}min')
        return df

    def extract_initial_waypoints(self, waypoints_coords_str):
        """
        Extrait les n premiers points de passage d'un trajet
        """
        try:
            waypoints = json.loads(waypoints_coords_str)
            initial_points = []
            for point in waypoints[:self.num_points]:
                initial_points.extend([
                    point['start']['lat'],
                    point['start']['lng']
                ])
            return initial_points
        except:
            return None

    def calculate_route_similarity(self, coords1, coords2):
        """
        Calcule la similarité entre deux séquences de coordonnées
        """
        if not isinstance(coords1, list) or not isinstance(coords2, list):
            return 0.0

        if not coords1 or not coords2:
            return 0.0

        coords1 = np.array(coords1).reshape(-1, 2)
        coords2 = np.array(coords2).reshape(-1, 2)

        min_len = min(len(coords1), len(coords2))
        similar_points = 0

        for i in range(min_len):
            distance = np.sqrt(np.sum((coords1[i] - coords2[i])**2))
            if distance < self.similarity_threshold:
                similar_points += 1

        return similar_points / min_len

    def find_similar_routes_in_window(self, window_df):
        """
        Trouve les groupes de trajets similaires dans une fenêtre temporelle
        """
        route_points = []
        valid_indices = []

        # Utiliser l'index du DataFrame directement
        for idx in window_df.index:
            row = window_df.loc[idx]
            points = self.extract_initial_waypoints(row['points_passage_coords'])
            if points and len(points) >= 4:
                route_points.append(points)
                valid_indices.append(idx)

        if not route_points:
            return defaultdict(list), []

        X = np.array(route_points)
        if len(X) >= 2:  # Vérifier qu'il y a assez de points pour le clustering
            clustering = DBSCAN(eps=self.clustering_eps, min_samples=2).fit(X)
        else:
            return defaultdict(list), valid_indices

        clusters = defaultdict(list)
        for i, label in enumerate(clustering.labels_):
            if label >= 0:
                original_idx = valid_indices[i]
                clusters[label].append({
                    'index': original_idx,
                    'origin': window_df.loc[original_idx, 'lieu_prise_en_charge_long'],
                    'destination': window_df.loc[original_idx, 'destination_long'],
                    'points': route_points[i]
                })

        return clusters, valid_indices

    def analyze_routes(self, df, datetime_column, output_file='trajets_similaires.csv'):
        """
        Analyse et enrichit le DataFrame avec les résultats, en tenant compte des fenêtres temporelles
        """
        print(f"""
        Configuration de l'analyse :
        - Taille de la fenêtre temporelle : {self.time_window_minutes} minutes
        - Seuil de similarité : {self.similarity_threshold}
        - Nombre de points comparés : {self.num_points}
        - Paramètre eps du clustering : {self.clustering_eps}
        """)

        # Créer une copie du DataFrame pour éviter les modifications sur l'original
        df = df.copy()

        # Créer les fenêtres temporelles
        df = self.create_time_windows(df, datetime_column)

        # Vérifier les colonnes nécessaires
        required_columns = ['points_passage_coords', 'lieu_prise_en_charge_long', 'destination_long']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"Colonnes manquantes : {missing_columns}")
            return df

        # Initialiser les nouvelles colonnes
        df['groupe_similaire'] = -1
        df['similarite_moyenne'] = 0.0
        df['nombre_trajets_groupe'] = 0

        # Traiter chaque fenêtre temporelle séparément
        global_group_id = 0
        for window, window_df in df.groupby('date_time_window'):
            print(f"\nAnalyse de la fenêtre temporelle: {window}")

            similar_groups, valid_indices = self.find_similar_routes_in_window(window_df)

            # Pour chaque groupe dans la fenêtre
            for group_id, routes in similar_groups.items():
                if len(routes) >= 2:
                    similarities = []
                    indices = [route['index'] for route in routes]

                    for i in range(len(routes)):
                        for j in range(i+1, len(routes)):
                            sim = self.calculate_route_similarity(
                                routes[i]['points'],
                                routes[j]['points']
                            )
                            similarities.append(sim)

                    avg_similarity = np.mean(similarities) if similarities else 0

                    # Mettre à jour le DataFrame avec un ID de groupe global unique
                    for idx in indices:
                        df.loc[idx, 'groupe_similaire'] = int(global_group_id)
                        df.loc[idx, 'similarite_moyenne'] = round(avg_similarity * 100, 2)
                        df.loc[idx, 'nombre_trajets_groupe'] = len(routes)

                    global_group_id += 1

        # Sauvegarder les résultats
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\nRésultats sauvegardés dans {output_file}")

        # Afficher un résumé
        grouped_routes = df[df['groupe_similaire'] >= 0]
        print(f"\nNombre total de trajets groupés : {len(grouped_routes)}")
        print(f"Nombre total de groupes uniques : {grouped_routes['groupe_similaire'].nunique()}")

        # Afficher un résumé par fenêtre temporelle
        for window, window_group in grouped_routes.groupby('date_time_window'):
            print(f"\nFenêtre temporelle : {window}")
            print(f"Nombre de trajets groupés : {len(window_group)}")
            print(f"Nombre de groupes : {window_group['groupe_similaire'].nunique()}")

        return df
# Exemple d'utilisation
"""
# Configuration avec fenêtre de 30 minutes
analyzer = RouteAnalyzer(
    time_window_minutes=30,
    similarity_threshold=0.01,
    num_points=2,
    clustering_eps=0.01
)

# Utilisation
df_enrichi = analyzer.analyze_routes(
    df_data_enrichi,
    datetime_column='date_heure_prise_en_charge',
    output_file='trajets_similaires_par_fenetre.csv'
)
"""





# Configuration stricte
analyzer_strict = RouteAnalyzer(
    time_window_minutes=60, # Configuration avec fenêtre de 30 minutes
    similarity_threshold=0.005,  # Points doivent être très proches
    num_points=5,               # Compare plus de points
    clustering_eps=0.005        # Clusters plus stricts
)

# Configuration permissive
analyzer_permissive = RouteAnalyzer(
    time_window_minutes=60, # Configuration avec fenêtre de 30 minutes
    similarity_threshold=0.02,   # Accepte des points plus éloignés
    num_points=2,               # Compare moins de points
    clustering_eps=0.02         # Clusters plus larges
)

df_data_enrichi = pd.read_csv('transport_data_enrichi.csv')

# Utilisation
df_enrichi_final_strict = analyzer_strict.analyze_routes(
    df_data_enrichi,
    datetime_column='date_heure_prise_en_charge',
    output_file='trajets_similaires_par_fenetre_strict.csv'
)

# ou
df_enrichi_final_permissive = analyzer_permissive.analyze_routes(
    df_data_enrichi,
    datetime_column='date_heure_prise_en_charge',
    output_file='trajets_similaires_par_fenetre_permissif.csv'
  )

