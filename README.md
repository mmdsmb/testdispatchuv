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

#### Using psycopg2
```python
import psycopg2
from app.core.config import settings

conn = psycopg2.connect(
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
docker run -p 8000:8000 fastapi-app
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