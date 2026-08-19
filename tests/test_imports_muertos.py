"""
Que no se acumulen imports que ya no usa nadie.

El proyecto no tiene linter (`AGENTS.md`: "No configured tooling"), así que
nada los detecta y se van quedando. Cuando se escribió este test había
diecisiete, varios de ellos restos de refactors recientes: `library_service`
seguía importando seis scorers que ya construye el catálogo.

No es una manía de limpieza. Un import que sobra dice que ese módulo depende
de algo de lo que ya no depende, y eso es justo lo que uno mira para
entender un fichero.
"""
import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _importados(arbol) -> dict[str, int]:
    """Nombre local de cada import y en qué línea está."""
    nombres = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                nombres[(alias.asname or alias.name).split(".")[0]] = nodo.lineno
        elif isinstance(nodo, ast.ImportFrom):
            for alias in nodo.names:
                if alias.name != "*":
                    nombres[alias.asname or alias.name] = nodo.lineno
    return nombres


def _muertos(fichero: Path) -> list[str]:
    texto = fichero.read_text()
    arbol = ast.parse(texto)

    usados = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    usados |= {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    # `__all__` cuenta como uso: reexportar es para lo que está.
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            usados.add(nodo.value)

    lineas = texto.splitlines()
    muertos = []
    for nombre, linea in _importados(arbol).items():
        if nombre in usados:
            continue
        # `from __future__ import annotations` no se "usa" pero hace falta.
        if nombre == "annotations":
            continue
        # Última red: que no aparezca en ninguna otra línea (anotaciones en
        # cadena, docstrings que lo nombran).
        if any(nombre in l for i, l in enumerate(lineas, 1) if i != linea):
            continue
        muertos.append(f"{fichero.relative_to(RAIZ)}:{linea} {nombre}")
    return muertos


def test_no_hay_imports_sin_usar():
    culpables = []
    for fichero in (RAIZ / "puntueitor").rglob("*.py"):
        if "__pycache__" in fichero.parts:
            continue
        culpables.extend(_muertos(fichero))

    assert not culpables, (
        f"{len(culpables)} imports sin usar:\n  " + "\n  ".join(sorted(culpables))
    )
