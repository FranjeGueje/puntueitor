#!/usr/bin/env bash
set -euo pipefail

APP_NAME="puntueitor"
ENTRY_POINT="puntueitor/gui/app.py"

cd "$(dirname "$0")"

echo "==> Activando virtualenv..."
source .venv/bin/activate

echo "==> Instalando PyInstaller..."
pip install -q pyinstaller

echo "==> Limpiando builds anteriores..."
rm -rf build dist *.spec

echo "==> Ejecutando PyInstaller..."
pyinstaller \
    --onefile \
    --name "$APP_NAME" \
    --add-data "puntueitor/gui/styles.tcss:." \
    --collect-all textual \
    --hidden-import igdbpy \
    --hidden-import howlongtobeatpy \
    --hidden-import igdbpy \
    --hidden-import requests \
    --hidden-import steampy \
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
echo "==> Build completado: $(pwd)/dist/$APP_NAME"
ls -lh "dist/$APP_NAME"
