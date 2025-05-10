
-- Créez d'abord la fonction
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

create table chauffeurBronze (
    horodateur text,
    prenom_nom text,
    telephone text,
    email text primary key,
    type_chauffeur text,
    nombre_places text,
    disponible_22_debut text,
    disponible_22_fin text,
    disponible_23_debut text,
    disponible_23_fin text,
    disponible_24_debut text,
    disponible_24_fin text,
    disponible_25_debut text,
    disponible_25_fin text,
    code_postal text,
    carburant text,
    commentaires text,
    created_at timestamp with time zone default timezone('utc'::text, now()),
    updated_at timestamp with time zone default timezone('utc'::text, now())
);

ALTER TABLE chauffeurBronze
ADD COLUMN IF NOT EXISTS evenement_annee INTEGER,
ADD COLUMN IF NOT EXISTS evenement_jour TEXT;

-- Trigger pour mettre à jour updated_at
create trigger set_updated_at
    before update on chauffeurBronze
    for each row
    execute function update_updated_at_column();

CREATE TABLE IF NOT EXISTS "Hotes" (
    "ID" INTEGER PRIMARY KEY,
    "Prenom-Nom" TEXT,
    "Telephone" TEXT,
    "Nombre-prs-AR" TEXT,
    "Provenance" TEXT,
    "Arrivee-date" TEXT,
    "Arrivee-vol" TEXT,
    "Arrivee-heure" TEXT,
    "Arrivee-Lieux" TEXT,
    "Hebergeur" TEXT,
    "RESTAURATION" TEXT,
    "Telephone-hebergeur" TEXT,
    "Adresse-hebergement" TEXT,
    "Retour-date" TEXT,
    "Nombre-prs-Ret" TEXT,
    "Retour-vol" TEXT,
    "Retour-heure" TEXT,
    "Retour-Lieux" TEXT,
    "Destination" TEXT,
    "Chauffeur" TEXT
);

ALTER TABLE "Hotes"
ADD COLUMN IF NOT EXISTS evenement_annee INTEGER,
ADD COLUMN IF NOT EXISTS evenement_jour TEXT,
ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

-- Trigger pour mettre à jour updated_at
create trigger set_updated_at
    before update on "Hotes" 
    for each row
    execute function update_updated_at_column();



CREATE TABLE IF NOT EXISTS dispoChauffeur (
	chauffeur_id bigint NOT NULL,
	dispo_id serial NOT NULL,
	date_debut timestamp with time zone NOT NULL,
	date_fin timestamp with time zone NOT NULL,
	PRIMARY KEY (dispo_id)
);

CREATE TABLE IF NOT EXISTS adresseGps (
	hash_address varchar(255) NOT NULL,
	address varchar(255) NOT NULL,
	latitude double precision NOT NULL,
	longitude double precision NOT NULL,
	PRIMARY KEY (hash_address)
);

CREATE TABLE IF NOT EXISTS course (
	course_id serial NOT NULL,
	prenom_nom varchar(255) NOT NULL,
	telephone varchar(255) NOT NULL,
	nombre_personne bigint NOT NULL,
	lieu_prise_en_charge varchar(255) NOT NULL,
	date_heure_prise_en_charge timestamp with time zone NOT NULL,
	num_vol varchar(255),
	destination varchar(255) NOT NULL,
	hebergeur varchar(255),
	telephone_hebergement varchar(255),
	hash_lieu_prise_en_charge varchar(255),
	hash_destination varchar(255),
	date_time_window timestamp with time zone,
	hash_route varchar(255),
	groupe_id bigint,
	vip boolean,
	hote_id bigint,
	PRIMARY KEY (course_id)
);

CREATE TABLE IF NOT EXISTS courseGroupe (
	groupe_id serial NOT NULL,
	date_heure_prise_en_charge timestamp with time zone,
	nombre_personne bigint NOT NULL,
	vip boolean NOT NULL,
	lieu_prise_en_charge varchar(255),
	destination varchar(255),
	lieu_prise_en_charge_json jsonb,
	destination_json jsonb,
	date_heure_prise_en_charge_json jsonb,
	hash_lieu_prise_en_charge varchar(255),
	hash_destination varchar(255),
	date_time_window timestamp with time zone,
	hash_route varchar(255),
	PRIMARY KEY (groupe_id)
);

CREATE TABLE IF NOT EXISTS chauffeurAffectation (
	id serial NOT NULL,
	groupe_id bigint NOT NULL,
	nombre_personne_prise_en_charge bigint,
	chauffeur_id bigint NOT NULL,
	prenom_nom_chauffeur varchar(255),
	nombre_place_chauffeur bigint,
	telephone_chauffeur varchar(255),
	date_heure_prise_en_charge timestamp with time zone,
	lieu_prise_en_charge varchar(255),
	destination varchar(255),
	statut_affectation varchar(255) NOT NULL DEFAULT 'draft',
	date_accepted timestamp with time zone,
	date_done timestamp with time zone,
	partager_avec_chauffeur_json jsonb,
	course_combinee_id varchar(255),
	course_combinee boolean,
	date_created timestamp with time zone,
	date_pending timestamp with time zone,
	vip boolean,
	duree_trajet_min bigint,
	combiner_avec_groupe_id bigint,
	passagers_json jsonb,
	course_partagee boolean,
	details_course_combinee_json jsonb,
	prenom_nom_list TEXT,
	PRIMARY KEY (id)
);


CREATE TABLE IF NOT EXISTS chauffeur (
	chauffeur_id serial NOT NULL,
	email varchar(255) NOT NULL UNIQUE,
	prenom_nom varchar(255) NOT NULL,
	nombre_place bigint NOT NULL,
	telephone varchar(255) NOT NULL,
	carburant varchar(255),
	adresse varchar(255),
	code_postal varchar(255) NOT NULL,
	commentaires varchar(2000),
	actif boolean,
	avec_voiture boolean,
	hash_adresse varchar(255),
	PRIMARY KEY (chauffeur_id)
);

CREATE TABLE IF NOT EXISTS courseCalcul (
	hash_route varchar(255) NOT NULL,
	lieu_prise_en_charge TEXT,
	destination TEXT,
	lieu_prise_en_charge_lat float,
	lieu_prise_en_charge_lng float,
	destination_lat float,
	destination_lng float,
	distance_vol_oiseau_km float,
	distance_routiere_km float,
	duree_trajet_min float,
	duree_trajet_secondes bigint,
	points_passage TEXT,
	points_passage_coords TEXT,
	PRIMARY KEY (hash_route)
);

CREATE TABLE IF NOT EXISTS configuration (
	id integer NOT NULL,
	duree_groupe bigint,
	destination_dans_groupage boolean,
	time_zone varchar(255),
	pays_organisateur varchar(255),
	adresse_salle varchar(255),
	jour_evenement date,
	heure_prise_en_charge bigint,
	minute_prise_en_charge bigint,
	jour_fin_evenement date,
	nombre_minutes_avant_retour bigint,
	duree_entre_mission_chauffeur bigint,
	groupe_priorite_vanne bigint,
	capacite_vehicule jsonb,
	date_columns varchar(255),
	file_path_client jsonb,
	file_path_chauffeur bigint,
	FILE_PATH_TRANSFORMED_CLIENT varchar(255),
	FILE_PATH_TRANSFORMED_CHAUFFEUR varchar(255),
	google_maps_api_key varchar(255),
	google_maps_api_url varchar(255),
	client_columns_mapping_arrivee jsonb NOT NULL,
	client_columns_mapping_salle jsonb NOT NULL,
	chauffeur_columns_mapping jsonb NOT NULL,
	client_columns_mapping_retour jsonb NOT NULL,
	disponibilite_columns jsonb NOT NULL,
	disponibilite_columns_mapping jsonb NOT NULL,
	lieux_mapping_adresse jsonb NOT NULL,
	actif boolean NOT NULL,
	PRIMARY KEY (id)
);

ALTER TABLE dispoChauffeur ADD CONSTRAINT dispoChauffeur_fk0 FOREIGN KEY (chauffeur_id) REFERENCES chauffeur(chauffeur_id);

ALTER TABLE course ADD CONSTRAINT course_fk10 FOREIGN KEY (hash_lieu_prise_en_charge) REFERENCES adresseGps(hash_address);

ALTER TABLE course ADD CONSTRAINT course_fk11 FOREIGN KEY (hash_destination) REFERENCES adresseGps(hash_address);

ALTER TABLE course ADD CONSTRAINT course_fk13 FOREIGN KEY (hash_route) REFERENCES courseCalcul(hash_route);

ALTER TABLE chauffeurAffectation ADD CONSTRAINT chauffeurAffectation_fk1 FOREIGN KEY (groupe_id) REFERENCES courseGroupe(groupe_id);

ALTER TABLE chauffeurAffectation ADD CONSTRAINT chauffeurAffectation_fk3 FOREIGN KEY (chauffeur_id) REFERENCES chauffeur(chauffeur_id);
ALTER TABLE chauffeur ADD CONSTRAINT chauffeur_fk11 FOREIGN KEY (hash_adresse) REFERENCES adresseGps(hash_address);

ALTER TABLE chauffeurAffectation ADD CONSTRAINT unique_groupe_chauffeur UNIQUE (groupe_id, chauffeur_id);
