
## 🚀 Deployment

### Local Docker
si la commande docker ne fonctionne pas dans un shall zhs

```bash
nano ~/.zshrc
# ajoute cette ligne si ca  nexiste pas
export PATH="/usr/local/bin:$PATH"
export PATH="/Applications/Docker.app/Contents/Resources/bin/docker:$PATH"

```
```bash
source ~/.zshrc
```

```bash
docker build -t fastapi-app .

docker run --env-file .env -p 8080:8080 fastapi-app
#docker run -p 8080:8080 fastapi-app

# OU 
docker build -t fastapi-app . && docker run --env-file .env -p 8080:8080 fastapi-app

docker exec -it 1e572707f5e7623e14b69b448283b5390cb6f1fa66aa221ed2bfa45ba4700ff4 bash

docker exec -it sad_lehmann bash

docker ps --filter "status=running"  # Ne montre que les conteneurs en cours d'exécution.

# Copier le fichier vers votre machine
docker cp <nom_conteneur>:/chemin/fichier.txt .

# Éditez avec votre éditeur local (VS Code, nano, etc.)
nano fichier.txt

# Remettre dans le conteneur
docker cp fichier.txt <nom_conteneur>:/chemin/fichier.txt
docker cp flask_app/dispatch.py  wizardly_solomon:/app/flask_app/dispatch.py
docker cp test_dispatch.py  nifty_kare:test_dispatch.py
docker cp app/core/dispatch_solver.py nifty_kare:/app/app/core/dispatch_solver.py

#Pour récupérer uniquement les noms des conteneurs Docker actifs (en cours d'exécution) qui contiennent un terme spécifique comme "wiz", voici la commande optimale :
$ docker ps -a --format "{{.Names}}" | grep "wiz"

# Si plusieurs résultats : utilisez un filtre plus précis comme grep "^fastapi"
docker ps -a --format "table {{.ID}}\t{{.Names}}\t{{.Status}}" | grep -E "fast[^-]"

docker logs [NOM_DU_CONTENEUR]  # Voir les logs
docker exec -it [NOM_DU_CONTENEUR] bash  # Entrer dans le conteneur


Pour arrêter un conteneur Docker en cours d'exécution, vous pouvez utiliser la commande suivante :

```bash
#docker kill <container_id_ou_nom>
docker stop  affectionate_turing
```

Remplacez `<container_id_ou_nom>` par l'ID ou le nom du conteneur que vous souhaitez arrêter. Vous pouvez obtenir l'ID ou le nom du conteneur en utilisant la commande :

```bash
docker ps
```

Cette commande liste tous les conteneurs en cours d'exécution.

Si vous préférez arrêter le conteneur de manière plus propre (en lui donnant le temps de terminer ses processus), utilisez :

```bash
#docker stop <container_id_ou_nom>

docker stop  affectionate_turing
```

Cela enverra un signal `SIGTERM` au conteneur, puis un `SIGKILL` après un délai de grâce (par défaut 10 secondes).
