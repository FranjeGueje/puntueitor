"""
Que los mensajes manden al usuario al sitio que existe.

Cuando algo no funciona, lo único que tiene el usuario es la frase del aviso.
Si le dice "Opciones → Configuración" y ese menú se llama otra cosa —o peor,
existe pero ya no guarda lo que hay que tocar—, el mensaje deja de ayudar
justo cuando más falta hace.

Ya pasó: las credenciales se movieron a Cuentas y media docena de avisos
siguieron mandando a Configuración durante todo un refactor. Esto lo caza
leyendo el código fuente, que es la única forma de cubrirlos todos sin tener
que provocar cada error uno a uno.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

#: Los menús que existen de verdad, tal y como se llaman en pantalla.
MENUS = {"Cuentas", "Tiendas", "Puntueitor3D", "Avanzado", "Créditos"}

#: Dónde se escriben los avisos que ve el usuario.
FUENTES = sorted(
    p for p in (RAIZ / "puntueitor").rglob("*.py")
    if "__pycache__" not in p.parts
)

#: "Opciones → Algo", que es como se le dice a dónde ir.
INDICACION = re.compile(r"Opciones\s*→\s*([A-Za-zÁÉÍÓÚáéíóúñÑ0-9]+)")


def _indicaciones():
    for fichero in FUENTES:
        for numero, linea in enumerate(fichero.read_text().splitlines(), 1):
            for destino in INDICACION.findall(linea):
                yield fichero.relative_to(RAIZ), numero, destino


def test_every_pointer_names_a_menu_that_exists():
    rotas = [
        f"{ruta}:{numero} → {destino}"
        for ruta, numero, destino in _indicaciones()
        if destino not in MENUS
    ]
    assert not rotas, (
        "estos avisos mandan a un menú que no existe: " + ", ".join(rotas)
    )


def test_there_are_pointers_at_all():
    """
    Si el formato cambiara (otra flecha, otra redacción), lo de arriba
    pasaría sin comprobar nada. Esto avisa de que se ha quedado ciego.
    """
    assert len(list(_indicaciones())) >= 5


@pytest.mark.parametrize("palabra", ["API key", "Steam ID", "credenciales"])
def test_credentials_send_you_to_cuentas(palabra):
    """
    Lo que se arregla en Cuentas tiene que mandar a Cuentas. Mandarlo a
    Tiendas —donde ya solo están las casillas— es exactamente el fallo que
    dejó el refactor anterior.
    """
    for fichero in FUENTES:
        for linea in fichero.read_text().splitlines():
            if palabra in linea and "Opciones →" in linea:
                assert "Cuentas" in linea, f"{fichero.name}: {linea.strip()}"
