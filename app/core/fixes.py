"""
Fixes temporaires pour le processeur de courses.

Ce fichier contient des corrections temporaires pour résoudre le problème
de valeurs null dans les champs obligatoires.
"""
from typing import List, Dict
import pandas as pd

def fix_course_data(course_data: Dict) -> Dict:
    """Corrige les données d'une course pour éviter les valeurs nulles."""
    required_fields = ['lieu_prise_en_charge', 'destination']
    for field in required_fields:
        if not course_data.get(field):
            raise ValueError(f"Champ requis manquant : {field}")
    return course_data

def validate_course_row(row: pd.Series) -> bool:
    """Valide une ligne de course pour vérifier que tous les champs requis sont présents."""
    required_aller = ['Arrivee-Lieux', 'Adresse-hebergement']
    required_retour = ['Retour-Lieux', 'Adresse-hebergement'] 
    
    if pd.notnull(row.get('erreur_aller')) and row['erreur_aller']:
        return False
        
    if pd.notnull(row.get('erreur_retour')) and row['erreur_retour']:
        return False
        
    for field in required_aller:
        if not pd.notnull(row.get(field)) or str(row[field]).strip() == '':
            return False
            
    for field in required_retour:
        if not pd.notnull(row.get(field)) or str(row[field]).strip() == '':
            return False
            
    return True
