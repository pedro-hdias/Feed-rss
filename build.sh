#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python não encontrado: $PYTHON_BIN" >&2
  echo "Defina PYTHON_BIN, por exemplo: PYTHON_BIN=python ./build.sh" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  "$PYTHON_BIN" -m venv .venv
fi

VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  echo "O ambiente virtual não criou .venv/bin/python." >&2
  echo "No Git Bash do Windows, use build.ps1 para gerar o .exe." >&2
  exit 1
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r requirements.txt
"$VENV_PYTHON" -m PyInstaller --noconfirm --clean --windowed --name JWNoticiasFeed main.py
echo "Executável criado em: $PROJECT_DIR/dist/JWNoticiasFeed/JWNoticiasFeed"
