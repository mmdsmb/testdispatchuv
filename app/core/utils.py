import hashlib
from math import radians, sin, cos, sqrt, atan2

def generate_address_hash(address: str) -> str:
    """Génère un hash MD5 standardisé pour les adresses"""
    return hashlib.md5(address.strip().lower().encode('utf-8')).hexdigest()

def generate_route_hash(pickup_address: str, destination_address: str) -> str:
    """Génère un hash unique pour un trajet (combinaison des deux adresses)"""
    combined = f"{pickup_address.strip().lower()}_{destination_address.strip().lower()}"
    return generate_address_hash(combined)

def calculate_bird_distance(origin_lat: float, origin_lng: float, 
                          dest_lat: float, dest_lng: float) -> float:
    """Calcule la distance à vol d'oiseau en km (formule Haversine)"""
    R = 6371  # Rayon de la Terre en km
    lat1, lon1, lat2, lon2 = map(radians, [origin_lat, origin_lng, dest_lat, dest_lng])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return round(R * c, 2)
