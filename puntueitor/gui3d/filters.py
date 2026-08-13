"""
Estado de los filtros del carrusel y cómo se aplican.

Aparte de `app.py` para que "qué juegos entran" se pueda leer (y probar) de
una vez, sin tener que reconstruir la aplicación entera.

Los tres filtros de estado (terminado, favorito, backlog) son de TRES
valores, no de dos: sin filtrar, solo los que sí, o solo los que no. Con un
simple booleano no habría forma de decir "me da igual", que es justo el
estado en el que están casi siempre.
"""
from dataclasses import dataclass

#: Los tres valores por los que va rotando un filtro de estado, en orden.
#: `None` es "no filtrar por esto" y es el que se enseña como "N/A".
TRISTATE_CYCLE = (None, True, False)

TRISTATE_LABELS = {None: "N/A", True: "Sí", False: "No"}


def cycle_tristate(value: bool | None, direction: int) -> bool | None:
    """El siguiente (o anterior) valor de un filtro de estado, dando la vuelta."""
    index = TRISTATE_CYCLE.index(value)
    return TRISTATE_CYCLE[(index + direction) % len(TRISTATE_CYCLE)]


@dataclass
class Filters:
    """
    Los filtros activos. Todo a None significa "no filtrar nada".

    `hidden` va aparte del resto (no está aquí, vive en `app.App`) porque no
    se elige en este menú sino con su propio botón (L2), y porque su valor
    por defecto no es "no filtrar" sino "esconder los ocultos".
    """

    name: str | None = None
    max_duration: float | None = None
    finished: bool | None = None
    favorite: bool | None = None
    backlog: bool | None = None

    def clear(self) -> None:
        self.name = None
        self.max_duration = None
        self.finished = None
        self.favorite = None
        self.backlog = None

    @property
    def any_active(self) -> bool:
        return any((
            self.name, self.max_duration is not None,
            self.finished is not None, self.favorite is not None,
            self.backlog is not None,
        ))

    def matches(self, game) -> bool:
        """¿Pasa este juego todos los filtros activos?"""
        if game is None:
            # Sin ficha no hay nada que comprobar; solo se deja pasar si no
            # hay ningún filtro puesto, porque si no aparecerían juegos que
            # no cumplen nada entre los que sí.
            return not self.any_active

        if self.name and self.name.lower() not in game.title.lower():
            return False

        if self.max_duration is not None:
            # Un juego sin duración conocida NO pasa el filtro de duración:
            # el filtro dice "que dure como mucho X", y de este no se sabe
            # si dura más o menos. Colarlo sería afirmar algo que no consta.
            if game.duration_hours is None or game.duration_hours > self.max_duration:
                return False

        for field in ("finished", "favorite", "backlog"):
            wanted = getattr(self, field)
            if wanted is not None and bool(getattr(game, field)) != wanted:
                return False

        return True


def parse_number(text: str) -> float | None:
    """
    Lee un número escrito a mano. Devuelve None si no se entiende.

    Se acepta la coma además del punto: en un teclado español es lo que sale
    de la tecla decimal, y "12,5" es lo que uno escribe sin pensar.
    """
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_duration(text: str) -> float | None:
    """
    Lee la duración máxima escrita a mano. Devuelve None si no se entiende
    o si está vacía, que es lo mismo que "sin filtro de duración".
    """
    value = parse_number(text)
    return value if value is not None and value > 0 else None
