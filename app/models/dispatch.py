from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr

class AdresseGps(BaseModel):
    hash_address: str
    address: str
    latitude: float
    longitude: float

    class Config:
        from_attributes = True

class Chauffeur(BaseModel):
    chauffeur_id: int
    email: EmailStr
    prenom_nom: str
    nombre_place: int
    telephone: str
    carburant: Optional[str] = None
    adresse: Optional[str] = None
    code_postal: str
    commentaires: Optional[str] = None
    actif: Optional[bool] = None
    avec_voiture: Optional[bool] = None
    hash_adresse: Optional[str] = None

    class Config:
        from_attributes = True

class DispoChauffeur(BaseModel):
    dispo_id: int
    chauffeur_id: int
    date_debut: datetime
    date_fin: datetime

    class Config:
        from_attributes = True

class CourseCalcul(BaseModel):
    hash_route: str
    lieu_prise_en_charge: Optional[str] = None
    destination: Optional[str] = None
    lieu_prise_en_charge_lat: Optional[str] = None
    lieu_prise_en_charge_lng: Optional[int] = None
    destination_lat: Optional[str] = None
    destination_lng: Optional[str] = None
    distance_vol_oiseau_km: Optional[str] = None
    distance_routiere_km: Optional[str] = None
    duree_trajet_min: Optional[str] = None
    duree_trajet_secondes: Optional[int] = None
    points_passage: Optional[str] = None
    points_passage_coords: Optional[str] = None

    class Config:
        from_attributes = True

class Course(BaseModel):
    id: int
    date_heure_prise_en_charge: datetime
    adresse_depart: str
    adresse_arrivee: str
    latitude_depart: float
    longitude_depart: float
    latitude_arrivee: float
    longitude_arrivee: float
    statut: str
    groupe_id: Optional[int] = None

class CourseGroupe(BaseModel):
    groupe_id: int
    lieu_prise_en_charge_list: Optional[str] = None
    destination_list: Optional[str] = None
    date_heure_prise_en_charge_list: Optional[datetime] = None
    nombre_personne: int
    vip: bool

    class Config:
        from_attributes = True

class ChauffeurAffectation(BaseModel):
    id: int
    groupe_id: int
    nombre_personne_prise_en_charge: Optional[int] = None
    chauffeur_id: int
    prenom_nom_chauffeur: Optional[str] = None
    nombre_place_chauffeur: Optional[int] = None
    telephone_chauffeur: Optional[str] = None
    statut_affectation: str = Field(default="draft")
    date_accepted: Optional[datetime] = None
    date_done: Optional[datetime] = None
    partager_avec_chauffeur_json: Optional[dict] = None
    course_combinee_id: Optional[str] = None
    course_combinee: Optional[bool] = None
    date_created: Optional[datetime] = None
    date_pending: Optional[datetime] = None
    vip: Optional[bool] = None
    duree_trajet_min: Optional[int] = None
    combiner_avec_groupe_id: Optional[int] = None
    passagers_json: Optional[dict] = None
    course_partagee: Optional[bool] = None
    details_course_combinee_json: Optional[dict] = None

    class Config:
        from_attributes = True

# Schémas de requête pour les paramètres temporels
class TimeWindowParams(BaseModel):
    date_heure_debut: Optional[datetime] = None
    date_heure_fin: Optional[datetime] = None

class Adresse(BaseModel):
    id: int
    adresse: str
    latitude: float
    longitude: float

class Affectation(BaseModel):
    id: int
    chauffeur_id: int
    course_id: int
    groupe_id: int
    date_creation: datetime
    statut: str

class AffectationCreate(BaseModel):
    chauffeur_id: int
    course_ids: List[int]
    groupe_id: int

class AffectationUpdate(BaseModel):
    chauffeur_id: Optional[int] = None
    statut: Optional[str] = None 