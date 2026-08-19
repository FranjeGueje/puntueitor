#!/usr/bin/env bash
set -euo pipefail

APP_NAME="puntueitor"
ENTRY_POINT="puntueitor/tui/app.py"

cd "$(dirname "$0")"

echo "==> Activando virtualenv..."
source .venv/bin/activate

echo "==> Instalando PyInstaller..."
pip install -q pyinstaller

# Extraer versión desde puntueitor/__init__.py
VERSION=$(python -c "from puntueitor import __version__; print(__version__)")
ARCH=$(uname -m)
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
OUTPUT_NAME="${APP_NAME}-${VERSION}-${ARCH}-${OS}"

echo "==> Limpiando builds anteriores..."
rm -rf build dist/"$OUTPUT_NAME" *.spec

echo "==> Ejecutando PyInstaller..."
pyinstaller \
    --onefile \
    --name "$OUTPUT_NAME" \
    --add-data "puntueitor/tui/styles.tcss:." \
    --collect-all textual \
    --hidden-import igdbpy \
    --hidden-import howlongtobeatpy \
    --hidden-import requests \
    --hidden-import threading \
    --hidden-import concurrent.futures \
    --hidden-import logging \
    --hidden-import json \
    --hidden-import sqlite3 \
    --hidden-import pathlib \
    --hidden-import tempfile \
    --hidden-import shutil \
    --hidden-import importlib.resources \
    --hidden-import dataclasses \
    --hidden-import enum \
    --hidden-import math \
    --paths . \
    "$ENTRY_POINT"

echo ""
echo "==> Build completado: $(pwd)/dist/$OUTPUT_NAME"
ls -lh "dist/$OUTPUT_NAME"
