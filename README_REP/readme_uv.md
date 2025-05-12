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

Configuration alternative (si vous utilisez WSL) ou CODESPACE
Si vous utilisez WSL (Windows Subsystem for Linux) :
Exécutez le script d'installation dans WSL :
```bash
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
```WICH



2. Create and activate a virtual environment:
```bash
which python # where python Windows 
# /c/Users/SAMBAMX/AppData/Local/Microsoft/WindowsApps/python # Windows path example

#uv venv si vous installer la version par defaut de python
uv venv --python=/opt/homebrew/opt/python@3.9/bin/python3.9
uv venv --python=/usr/bin/python3.9 # on code space
# uv venv --python=/c/Users/SAMBAMX/AppData/Local/Programs/Python/Python39 #windows
source .venv/bin/activate  # Sur Windows: .venv\Scripts\activate (via bash windows source .venv/Scripts/activate)
```

3. Install dependencies using uv:
```bash
uv pip install -e .

# This should resolve the parsing error and install the package along with the dev extras. Let me know if you'd like me to help with anything else!
uv pip install -e ".[dev]"
```



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


Pour exécuter les cellules dans le notebook avec l'environnement .venv (Python 3.9.22), vous devez d'abord installer le package ipykernel dans cet environnement. Voici les étapes à suivre :
Activer l'environnement virtuel :
Si vous utilisez un terminal, naviguez vers le répertoire du projet et activez l'environnement virtuel .venv.
Installer ipykernel :

```bash
uv pip install ipykernel
```


mis a  jour uv
```bash
uv pip uninstall uv

#upgrade uv
uv pip install --upgrade uv


```

```bash
uv --version
