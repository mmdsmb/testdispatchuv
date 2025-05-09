```bash
# Pour exécuter groupage simple date heure prise en charge,lieu prise en charge, destination
python -m app.scripts.test_grouping

# Pour exécuter avec une période spécifique
python test_dispatch.py --date_begin "2024-05-09 04:00:00" --date_end "2024-05-09 23:59:29"
python test_dispatch.py --date_begin "2024-05-09 04:00:00" --date_end "2024-05-09 12:59:29" --milp_timeout 120

python test_dispatch.py --date_begin "2024-05-10 04:00:00" --date_end "2024-05-10 23:59:29" --milp_timeout 300
# --milp_timeout 300 = 5 minutes

# Pour exécuter avec seulement une date de début
python test_dispatch.py --date_begin 2024-01-01 04:00:00

# Pour exécuter avec seulement une date de fin
python test_dispatch.py --date-end 2024-01-31

# Pour exécuter avec un timeout MILP personnalisé (en secondes)
python test_dispatch.py --date-begin 2024-01-01 --date-end 2024-01-31 --milp_timeout 600

# Pour exécuter sans paramètres (utilisera les valeurs par défaut)
python test_dispatch.py

```
