#!/usr/bin/env bash
#
# Arranca Puntueitor contra un directorio de pruebas, sin tocar nada de tu
# instalación de verdad.
#
#   tools/entorno-prueba.sh ~/pruebas-puntueitor
#   tools/entorno-prueba.sh ~/pruebas-puntueitor --3d
#   tools/entorno-prueba.sh ~/pruebas-puntueitor --shell
#   tools/entorno-prueba.sh ~/pruebas-puntueitor -- python -c 'import puntueitor'
#
# POR QUÉ SE FIJA `HOME` Y NO SOLO LAS `XDG_*`:
#
# `core/paths.py` resuelve los directorios base mirando primero las XDG_* y
# cayendo a `Path.home()`. Pero `migrate_legacy_paths()` usa `Path.home()`
# para el ORIGEN de las rutas antiguas (pre-XDG), que por definición cuelgan
# del home. Con las XDG_* apuntando al sandbox y `HOME` sin tocar, arrancar
# MOVERÍA tu `~/.cache/puntueitor/puntueitor.db` de verdad al directorio de
# pruebas. No es hipotético: es exactamente el accidente que documenta
# `tests/conftest.py`, y por eso allí se parchean también las dos vías.
#
# Se ponen las cinco variables, no solo `HOME`: si tu sesión ya exporta
# alguna XDG_* —muchos escritorios lo hacen—, esa ganaría a `HOME` y se
# escaparía del sandbox justo por el hueco que quedara sin cubrir.

set -euo pipefail

readonly REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rojo()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
gris()  { printf '\033[90m%s\033[0m\n' "$*"; }

uso() {
    cat <<'AYUDA'
Uso: tools/entorno-prueba.sh <directorio> [opciones] [-- comando...]

  <directorio>        Dónde vivirá el entorno de pruebas. Se crea si no está.

Opciones:
  --3d                Arranca el carrusel 3D en vez de la TUI.
  --shell             Abre una shell con el entorno puesto, sin arrancar nada.
  --copiar-config     Copia tu config.json real (credenciales de IGDB y Steam)
                      la primera vez, para no tener que volver a teclearlas.
                      NO copia sesiones ni biblioteca.
  --limpiar           Borra el contenido del directorio antes de empezar.
  -h, --help          Esto.

  -- comando...       Ejecuta ese comando dentro del entorno.

Todo lo que escriba la aplicación se queda dentro de <directorio>. Tu
instalación de verdad no se toca, ni siquiera se lee (salvo --copiar-config).
AYUDA
}

# ──────────────────────────────
# Argumentos
# ──────────────────────────────

DESTINO=""
MODO="tui"
COPIAR_CONFIG=0
LIMPIAR=0
COMANDO=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)       uso; exit 0 ;;
        --3d)            MODO="gui3d"; shift ;;
        --shell)         MODO="shell"; shift ;;
        --copiar-config) COPIAR_CONFIG=1; shift ;;
        --limpiar)       LIMPIAR=1; shift ;;
        --)              shift; COMANDO=("$@"); MODO="comando"; break ;;
        -*)              rojo "Opción desconocida: $1"; uso; exit 2 ;;
        *)
            if [[ -n "$DESTINO" ]]; then
                rojo "Sobra un argumento: $1"; uso; exit 2
            fi
            DESTINO="$1"; shift ;;
    esac
done

if [[ -z "$DESTINO" ]]; then
    rojo "Falta el directorio del entorno de pruebas."
    uso
    exit 2
fi

# ──────────────────────────────
# Red de seguridad
# ──────────────────────────────

HOME_REAL="$HOME"
CONFIG_REAL="${XDG_CONFIG_HOME:-$HOME_REAL/.config}/puntueitor/config.json"

mkdir -p "$DESTINO"
SANDBOX="$(cd "$DESTINO" && pwd)"

# El home de verdad como destino sería justo lo contrario de lo que hace
# este script. Se comprueba tras resolver la ruta: `~/../deck` es el mismo
# sitio escrito de otra forma y colaría en una comparación de cadenas.
if [[ "$SANDBOX" == "$HOME_REAL" ]]; then
    rojo "Ese directorio ES tu home. El entorno de pruebas tiene que ser otro."
    exit 1
fi

if [[ "$SANDBOX" == "/" || "$SANDBOX" == "$REPO" ]]; then
    rojo "Elige un directorio propio para las pruebas, no '$SANDBOX'."
    exit 1
fi

if [[ $LIMPIAR -eq 1 ]]; then
    gris "Vaciando $SANDBOX..."
    # Solo lo de dentro, y solo si el directorio es nuestro: borrar el
    # directorio entero y recrearlo se llevaría por delante un enlace
    # simbólico o un punto de montaje que el usuario hubiera puesto ahí.
    rm -rf -- "${SANDBOX:?}"/{config,data,cache,state,.config,.local,.cache}
fi

mkdir -p "$SANDBOX"/{config,data,cache,state}

# ──────────────────────────────
# El entorno
# ──────────────────────────────

export HOME="$SANDBOX"
export XDG_CONFIG_HOME="$SANDBOX/config"
export XDG_DATA_HOME="$SANDBOX/data"
export XDG_CACHE_HOME="$SANDBOX/cache"
export XDG_STATE_HOME="$SANDBOX/state"
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"

# Que se note en el prompt y en cualquier traza que esto no es lo de verdad.
export PUNTUEITOR_ENTORNO="pruebas"

if [[ $COPIAR_CONFIG -eq 1 ]]; then
    destino_config="$XDG_CONFIG_HOME/puntueitor/config.json"
    if [[ -f "$destino_config" ]]; then
        gris "Ya había un config.json en el entorno; no se pisa."
    elif [[ -f "$CONFIG_REAL" ]]; then
        mkdir -p "$(dirname "$destino_config")"
        cp -- "$CONFIG_REAL" "$destino_config"
        verde "Copiado tu config.json (credenciales) al entorno."
        gris "Las sesiones de tienda NO se copian: hay que iniciarlas aquí."
    else
        gris "No hay config.json real que copiar ($CONFIG_REAL)."
    fi
fi

PYTHON="$REPO/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="python3"

# ──────────────────────────────
# Comprobar el aislamiento ANTES de arrancar nada
# ──────────────────────────────
#
# Mismo criterio que `pytest_configure` en tests/conftest.py: si algo se ha
# escapado, es preferible no arrancar a descubrirlo cuando la aplicación ya
# haya escrito en los ficheros de verdad.
#
# Lo que se exige es que TODAS las rutas caigan DENTRO del sandbox, no que
# caigan fuera del home. Son cosas distintas y la segunda estaría mal: el
# sitio natural para un entorno de pruebas es `~/pruebas-puntueitor`, que
# está dentro del home y es perfectamente válido. Exigir que estén dentro
# del sandbox es además más estricto — cubre cualquier escape, no solo los
# que aterrizan en el home.

"$PYTHON" - "$SANDBOX" <<'COMPROBACION'
import sys
from pathlib import Path

from puntueitor.core import paths

sandbox = Path(sys.argv[1]).resolve()

rutas = {
    "config": paths.config_file(),
    "biblioteca": paths.main_db(),
    "marcas": paths.library_db(),
    "cache": paths.cache_dir(),
    "log": paths.log_file(),
}

# Los DESTINOS no bastan. Salen todos de las XDG_*, así que con `HOME`
# escapado seguirían cayendo dentro del sandbox y esto daría el visto bueno
# mientras la migración se lleva por delante los ficheros de verdad. Lo que
# hay que mirar son los ORÍGENES de `migrate_legacy_paths()`, que cuelgan de
# `Path.home()` — son los únicos que la aplicación MUEVE, no solo escribe, y
# por tanto los únicos que pueden destruir algo.
a_comprobar = dict(rutas)
a_comprobar["home"] = Path.home()
for origen, _ in paths._legacy_moves():
    a_comprobar[f"migración ({origen.name})"] = origen

for nombre, ruta in a_comprobar.items():
    try:
        ruta.resolve().relative_to(sandbox)
    except ValueError:
        sys.exit(
            f"AISLAMIENTO ROTO: {nombre} apuntaría a {ruta}, FUERA del "
            f"entorno de pruebas ({sandbox}). No se arranca."
        )

print("\n".join(f"  {nombre:12} {ruta}" for nombre, ruta in rutas.items()))
COMPROBACION

verde "Entorno de pruebas listo en $SANDBOX"
gris  "  HOME y las cuatro XDG_* apuntan ahí dentro. Tu instalación real no se toca."
echo

# ──────────────────────────────
# Arrancar
# ──────────────────────────────

cd "$REPO"

case "$MODO" in
    tui)
        gris "==> puntueitor.tui.app  (Ctrl-C o 'q' para salir)"
        exec "$PYTHON" -m puntueitor.tui.app
        ;;
    gui3d)
        gris "==> puntueitor.gui3d.app"
        exec "$PYTHON" -m puntueitor.gui3d.app
        ;;
    shell)
        gris "==> shell con el entorno puesto. 'exit' para volver."
        exec "${SHELL:-/bin/bash}"
        ;;
    comando)
        gris "==> ${COMANDO[*]}"
        exec "${COMANDO[@]}"
        ;;
esac
