select  "Retour-date" ,  TO_CHAR(
    TO_DATE("Retour-date", 'DD/MM/YYYY'), 
    'YYYY-MM-DD'
    ) from "Hotes"
    WHERE "Retour-date" ~ '^\d{2}/\d{2}/\d{4}$' 
    and "Retour-date" is not null;

select  "Arrivee-date" ,  TO_CHAR(
    TO_DATE("Arrivee-date", 'DD/MM/YYYY'), 
    'YYYY-MM-DD'
    ) from "Hotes"
    WHERE "Arrivee-date" ~ '^\d{2}/\d{2}/\d{4}$' 
    and "Arrivee-date" is not null;

-- Mise à jour du champ  Retour-date dans la table
UPDATE "Hotes"
SET "Retour-date" = TO_CHAR(
   TO_DATE("Retour-date", 'DD/MM/YYYY'), 
   'YYYY-MM-DD'
)
WHERE "Retour-date" ~ '^\d{2}/\d{2}/\d{4}$' 
and "Retour-date" is not null;

-- Mise à jour du champ Arrivee-date dans la table
UPDATE "Hotes"
SET "Arrivee-date" = TO_CHAR(
   TO_DATE("Arrivee-date", 'DD/MM/YYYY'), 
   'YYYY-MM-DD'
)
WHERE "Arrivee-date" ~ '^\d{2}/\d{2}/\d{4}$' 
and "Arrivee-date" is not null;


 -- Optionnel : vérifie le format
--ALTER TABLE course
--ADD COLUMN lieu_prise_en_charge_court varchar(255),
--ADD COLUMN destination_court varchar(255);