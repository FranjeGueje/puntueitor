"""
Los sistemas de scoring, tal y como los enseña el carrusel.

Fachada fina sobre `core/scoring/catalog.py`, que es donde viven de verdad
sus nombres, descripciones y forma de construirse. Antes esto era una copia
literal de los textos de la TUI —con un comentario explicando que copiar era
el precio de no arrastrar Textual dentro de la aplicación 3D—, y los dos
juegos de textos acabaron divergiendo, que es justo lo que aquel comentario
predecía.

El módulo se queda porque `menus.py` y `app.py` ya usan `SCORERS` y `BY_KEY`,
y porque el carrusel tiene una restricción propia: la descripción se pinta en
un marco de tamaño fijo, así que aquí se decide cuánto texto cabe.
"""
from puntueitor.core.scoring import catalog

#: Los sistemas, en orden. Son los `ScoringSystem` del catálogo tal cual: el
#: carrusel usa `key`, `name`, `title`, `description` y `config_form`.
SCORERS: tuple[catalog.ScoringSystem, ...] = catalog.SYSTEMS

BY_KEY: dict[str, catalog.ScoringSystem] = catalog.BY_KEY


def description_for(key: str) -> str:
    """
    Lo que se pinta en el marco de la derecha al recorrer la lista.

    Lleva la recomendación pegada al final: cabe, y es la frase que dice para
    qué sirve el sistema, que era lo único que el carrusel no enseñaba y la
    TUI sí.
    """
    sistema = catalog.get(key)
    if sistema is None:
        return ""
    return f"{sistema.description}\n\n{sistema.recommendation}"
