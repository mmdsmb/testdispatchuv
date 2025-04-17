# FastAPI Project

A structured FastAPI project with versioning and Supabase integration.

## 🚀 Features

- FastAPI with versioning
- Swagger UI & ReDoc documentation
- Supabase PostgreSQL integration
- Docker support
- Deployment configurations for Fly.io and Google Cloud Run
- Automated testing with pytest
- CI/CD with GitHub Actions

## 📋 Prerequisites

- Python 3.9+
- uv package manager
- Docker (for containerization)
- Fly.io CLI (for Fly.io deployment)
- Google Cloud SDK (for GCP deployment)
- PostgreSQL (for local development)

## 🛠 Installation

Prerecquis
Si brew n'est pas installée (macos)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

```bash
echo >> /Users/mustafa/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> /Users/mustafa/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
brew --version

brew install python@3.9
```

0. Clone the repository:
```bash
git clone <your-repo-url>
cd <your-repo-name>
```

1. Install uv:
```bash
curl -Ls https://astral.sh/uv/install.sh | sh

# To add $HOME/.local/bin to your PATH, either restart your shell or run:
source $HOME/.local/bin/env sh
source $HOME/.local/bin/env bash
source $HOME/.local/bin/env zsh
```

2. Create and activate a virtual environment:
```bash
which python # where python Windows 
# /c/Users/SAMBAMX/AppData/Local/Microsoft/WindowsApps/python # Windows path example

#uv venv si vous installer la version par defaut de python
uv venv --python=/opt/homebrew/opt/python@3.9/bin/python3.9
# uv venv --python=/c/Users/SAMBAMX/AppData/Local/Programs/Python/Python39 #windows
source .venv/bin/activate  # Sur Windows: .venv\Scripts\activate (via bash windows source .venv/Scripts/activate)
```

3. Install dependencies using uv:
```bash
uv pip install -e .
```

4. Copy the environment file:
```bash
cp .env.example .env
```

5. Update the `.env` file with your credentials

## 🏃‍♂️ Running Locally

Start the development server:
```bash
uvicorn app.main:app --reload
```

The API will be available at:
- API: http://localhost:8080
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

## 📚 API Endpoints

### Base Endpoints
- `GET /` - Hello World
- `GET /version` - Get API version

### Math Operations
- `GET /api/v1/sum?a=3&b=5` - Add two numbers
- `GET /api/v1/multiply?a=2&b=5` - Multiply two numbers

### Utilities
- `POST /api/v1/echo` - Echo JSON payload

### Items
- `POST /api/v1/items/upsert?item_id=1` - Upsert an item
  ```json
  {
    "name": "Test Item"
  }
  ```

## 🗃 Database Integration

### Supabase Setup

1. Create a new project on [Supabase](https://supabase.com)
2. Get OR create your database credentials from the project settings
```sql
CREATE USER myuser WITH PASSWORD 'mypassword';
GRANT CONNECT ON DATABASE postgres TO myuser;
GRANT USAGE ON SCHEMA public TO myuser;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO myuser;
```
3. Update your `.env` file with the credentials

### Connection Examples

#### Using SQLAlchemy
```python
from sqlalchemy import create_engine
from app.core.config import settings

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
```

#### Using psycopg
```python
import psycopg
from app.core.config import settings

conn = psycopg.connect(
    dbname=settings.POSTGRES_DB,
    user=settings.POSTGRES_USER,
    password=settings.POSTGRES_PASSWORD,
    host=settings.POSTGRES_SERVER
)
```

## 🧪 Testing

Run tests with pytest:
```bash
pytest
```

The test suite includes:
- API endpoint tests
- Database operation tests
- Integration tests

### Configuration de la base de données pour les tests

Le projet est configuré pour fonctionner avec deux environnements de base de données différents :

#### 1. Développement local avec Supabase

En environnement de développement, les tests utilisent la configuration Supabase définie dans le fichier `.env`. Cela permet de tester contre votre base de données cloud sans nécessiter d'installation PostgreSQL locale.

```
POSTGRES_SERVER=db.zpjemgpnfaeayofvnkzo.supabase.co
POSTGRES_USER=postgres
POSTGRES_PASSWORD=************
POSTGRES_DB=postgres
SQLALCHEMY_DATABASE_URI=postgresql+psycopg://postgres:************@db.zpjemgpnfaeayofvnkzo.supabase.co:5432/postgres
```

#### 2. Intégration continue (CI) avec PostgreSQL local

Dans l'environnement GitHub Actions CI, le système utilise automatiquement une base de données PostgreSQL locale définie dans le workflow :

```yaml
services:
  postgres:
    image: postgres:13
    env:
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
      POSTGRES_DB: test_db
```

#### Détection intelligente d'environnement

Le système détecte automatiquement l'environnement d'exécution :

```python
# Détecter si on est dans un environnement CI (GitHub Actions)
IN_CI = os.environ.get("CI") == "true"
```

#### Stratégies de test différentes

- **En développement (Supabase)** : Les tables existent déjà. Les tests nettoient uniquement les données.
- **En CI (PostgreSQL local)** : Les tables sont créées au début des tests et supprimées à la fin.

#### Exécution des tests

Pour exécuter les tests dans l'environnement actuel :
```bash
pytest
```

Pour exécuter un test spécifique uniquement :
```bash
pytest tests/test_database_connection.py -v
```

Pour vérifier la connectivité de la base de données :
```bash
pytest tests/test_database_connection.py::test_database_connection -v
```

## 🖋 Formatage du code

Le projet utilise des outils automatisés pour maintenir un style de code cohérent et de haute qualité.

### Black - Le formateur de code sans compromis

[Black](https://black.readthedocs.io/) est un formateur de code Python qui applique un style cohérent et déterministe à tout votre code. Contrairement à d'autres outils, Black est implacable et n'offre presque aucune option de configuration - c'est son principe fondamental : "N'argumentez pas sur le style de formatage".

#### Avantages de Black

- **Cohérence** : Garantit que tous les développeurs produisent du code formaté de la même manière
- **Gain de temps** : Élimine les discussions sur le style de code dans les revues
- **Lisibilité améliorée** : Produit du code avec un style visuellement cohérent
- **Intégration CI** : S'intègre à GitHub Actions pour vérifier automatiquement le formatage

#### Utilisation de Black

Pour formater tous les fichiers du projet :
```bash
black .
```

Pour vérifier si les fichiers sont bien formatés sans les modifier :
```bash
black . --check
```

### isort - Tri automatique des imports

[isort](https://pycqa.github.io/isort/) est un outil qui organise automatiquement les imports Python selon des règles précises :

1. **Groupement des imports** par type :
   - Imports de la bibliothèque standard Python (comme `os`, `sys`)
   - Imports tiers (comme `fastapi`, `sqlalchemy`)
   - Imports locaux (vos propres modules)

2. **Tri alphabétique** dans chaque groupe
   ```python
   # Bibliothèque standard
   import os
   import sys
   
   # Packages tiers
   from fastapi import FastAPI
   import sqlalchemy
   
   # Modules locaux
   from app.core import config
   from app.db import models
   ```

#### Pourquoi c'est important ?

- **Lisibilité** : Organisation cohérente des imports dans tous les fichiers
- **Maintenabilité** : Facilite la détection des dépendances inutiles ou manquantes
- **Collaboration** : Standard commun pour toute l'équipe
- **Prévention des conflits** : Évite les conflits de merge liés à l'ordre des imports

#### Configuration dans notre CI

Dans notre workflow GitHub Actions, isort s'exécute automatiquement :

```yaml
- name: Install and run isort
  run: |
    uv pip install --system isort
    isort .
```

#### Utilisation en développement

Pour vérifier vos imports localement :
```bash
# Appliquer le tri
isort .

# Vérifier sans modifier
isort . --check

# Voir les changements proposés
isort . --diff
```

#### Configuration avec Black

isort est configuré pour être compatible avec Black, assurant une cohérence parfaite entre les deux outils de formatage.

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

docker ps --filter "status=running"  # Ne montre que les conteneurs en cours d'exécution.

# Copier le fichier vers votre machine
docker cp <nom_conteneur>:/chemin/fichier.txt .

# Éditez avec votre éditeur local (VS Code, nano, etc.)
nano fichier.txt

# Remettre dans le conteneur
docker cp fichier.txt <nom_conteneur>:/chemin/fichier.txt
docker cp flask_app/dispatch.py  wizardly_solomon:/app/flask_app/dispatch.py

#Pour récupérer uniquement les noms des conteneurs Docker actifs (en cours d'exécution) qui contiennent un terme spécifique comme "wiz", voici la commande optimale :
$ docker ps -a --format "{{.Names}}" | grep "wiz"

# Si plusieurs résultats : utilisez un filtre plus précis comme grep "^fastapi"
docker ps -a --format "table {{.ID}}\t{{.Names}}\t{{.Status}}" | grep -E "fast[^-]"

docker logs [NOM_DU_CONTENEUR]  # Voir les logs
docker exec -it [NOM_DU_CONTENEUR] bash  # Entrer dans le conteneur
```



### Fly.io Deployment

1. Install Fly.io CLI:
```bash
curl -L https://fly.io/install.sh | sh
```

2. Login to Fly.io:
```bash
flyctl auth login
```

3. Launch the app:
```bash
flyctl launch
```

4. Deploy:
```bash
flyctl deploy
```

### Google Cloud Run Deployment

1. Build the container:
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/fastapi-app
```

2. Deploy to Cloud Run:
```bash
gcloud run deploy fastapi-app \
  --image gcr.io/YOUR_PROJECT_ID/fastapi-app \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

## 🔄 Adding New Routes

1. Create a new endpoint in `app/api/v1/endpoints.py`:
```python
@router.get("/new-endpoint", tags=["category"])
async def new_endpoint():
    return {"message": "New endpoint"}
```

2. The endpoint will be automatically available at `/api/v1/new-endpoint`

## 📝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 🔁 Git Setup

1. Initialize Git repository:
```bash
git init
```

2. Add files and commit:
```bash
git add .
git commit -m "Initial commit"
```

3. Add remote and push:
```bash
git config --global user.name "mmdsmb"
git config --global user.email "mmdsmb@gmail.com"
git remote add origin https://github.com/mmdsmb/testdispatchuv.git
git remote set-url origin git@github.com:mmdsmb/testdispatchuv.git
git push -u origin main
```



## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details. 


Réinstallez l'environnement virtuel

```bash
deactivate
rm -rf .venv
#uv venv si vous installer la version par defaut de python
uv venv --python=/opt/homebrew/opt/python@3.9/bin/python3.9
# uv venv --python=/c/Users/SAMBAMX/AppData/Local/Programs/Python/Python39 #windows
source .venv/bin/activate  # Sur Windows: .venv\Scripts\activate (via bash windows source .venv/Scripts/activate)
uv pip install -e .
uv pip install "psycopg[binary]"

```

```bash
history | tail -n 10
history | tail -n 50 | grep -i "docker" 
history | tail -n 50 | grep -i "docker" | less
#appuyer sur q pour quitter less
#pour executer un numéro de ligne 
# pour rexcuter une ligne  saisir !numéro eXEMPLE  !72 (RETURN)

```


