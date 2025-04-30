```bash
# Pour exécuter avec une période spécifique
python test_dispatch.py --date_begin "2024-05-09 04:00:00" --date_end "2024-05-09 23:59:29"
python test_dispatch.py --date_begin "2024-05-09 04:00:00" --date_end "2024-05-09 12:59:29"

# Pour exécuter avec seulement une date de début
python test_dispatch.py --date_begin 2024-01-01 04:00:00

# Pour exécuter avec seulement une date de fin
python test_dispatch.py --date-end 2024-01-31

# Pour exécuter avec un timeout MILP personnalisé (en secondes)
python test_dispatch.py --date-begin 2024-01-01 --date-end 2024-01-31 --milp-timeout 600

# Pour exécuter sans paramètres (utilisera les valeurs par défaut)
python test_dispatch.py

```
