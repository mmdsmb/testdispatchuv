
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