#!/bin/bash

# Install UV
curl -Ls https://astral.sh/uv/install.sh | sh

# Add $HOME/.local/bin to PATH
source $HOME/.local/bin/env sh
source $HOME/.local/bin/env bash
source $HOME/.local/bin/env zsh

# Alternative configuration for WSL or CODESPACE
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    source ~/.bashrc
fi

# Create and activate a virtual environment
which python
uv venv --python=/opt/homebrew/opt/python@3.9/bin/python3.9
source .venv/bin/activate

# Install dependencies
#uv pip install -e .
uv pip install -e ".[dev]" 