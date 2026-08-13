"""
Criterios de ordenación del carrusel y los "grupos" por los que saltan L1/R1.

Cada criterio define tres cosas:

    valor    de qué se ordena (nombre, nota, horas...)
    sentido  ascendente o descendente
    grupo    en qué tramo cae ese valor, para el salto rápido

El grupo es lo que hace que L1/R1 avancen "de golpe": por nombre es la
inicial (de la H a la I), y por nota o duración un tramo de cinco (de 70-74
a 75-79). Se calcula SIEMPRE a partir del mismo valor con el que se ordena,
no por separado, porque si las dos cosas no coincidieran los saltos irían a
sitios que no se corresponden con lo que se ve en el carrusel.

El sentido por defecto de cada criterio es el mismo que el de la TUI
(`gui/screens/sorting.py`): nombre y duración ascendentes, notas
descendentes — de una lista de notas lo que se quiere ver primero es lo
bueno, y de una de duraciones, lo corto.
"""
# NOTA: aquí hubo un criterio "media" que calculaba la nota con `MixedScore`
# y la configuración del usuario, como hace `LibraryService.sort`. Se
# sustituyó por la nota de SteamDB, que es un dato ya guardado en el juego:
# además de quitar de en medio la dependencia con `ConfigManager`, ordena
# por el mismo número que se ve en la pegatina de cada caja.
from collections.abc import Callable
from dataclasses import dataclass

from puntueitor.core.models import Game

#: Amplitud de los tramos numéricos (nota y duración): "de cinco en cinco".
NUMERIC_GROUP_SIZE = 5


def _numeric_group(value: float) -> int:
    """Tramo de cinco al que pertenece un valor: 0-4 -> 0, 5-9 -> 1..."""
    return int(value // NUMERIC_GROUP_SIZE)


def _name_group(value: str) -> str:
    """
    Inicial por la que agrupa un título.

    Los títulos que no empiezan por letra (hay unos cuantos: "112
    Operator", "60 Minutes to...") se quedan con su propio carácter, así que
    los números forman sus propios grupos al principio de la lista en vez de
    amontonarse todos en uno.
    """
    return value[:1].upper()


def _title_value() -> Callable[[Game], str]:
    # `title.lower()`, igual que la TUI, y no `title_normalized`: este último
    # quita artículos y signos para poder emparejar contra IGDB, así que
    # agrupar por su inicial daría saltos que no cuadran con lo que se lee
    # en pantalla.
    return lambda game: game.title.lower()


def _field_value(field: str) -> Callable[[], Callable[[Game], float | None]]:
    def factory() -> Callable[[Game], float | None]:
        return lambda game: getattr(game, field)
    return factory


def _name_group_label(group: object) -> str:
    # Hay juegos que empiezan por número ("112 Operator", "60 Minutes to...")
    # y forman su propio grupo, así que llamarlo "Letra: 1" sería mentira.
    if str(group).isalpha():
        return f"Letra: {group}"
    return f"Inicial: {group}"


def _score_group_label(prefix: str) -> Callable[[object], str]:
    """
    Etiqueta de un tramo de nota, con el nombre de QUÉ nota es delante
    ("Usuarios: 95", "Crítica: 90", "SteamDB: 85"): en el aviso no se ve de
    qué ordenación se viene, así que un "Puntuación: 95" a secas no dice
    cuál de las tres se está mirando.

    Se enseña solo el extremo BAJO, no el rango. Las notas llegan hasta 100,
    así que el último tramo salía como "100-104": un intervalo que no existe,
    en el que además solo cabe un valor. Con el extremo bajo se lee como "de
    aquí para arriba", que es lo que significa, y el caso del 100 deja de
    cantar.
    """
    def label(group: object) -> str:
        return f"{prefix}: {int(group) * NUMERIC_GROUP_SIZE}"
    return label


def _duration_group_label(group: object) -> str:
    # Aquí sí se enseña el rango: las horas no tienen tope, así que ningún
    # tramo queda cortado como el 100 de las notas.
    low = int(group) * NUMERIC_GROUP_SIZE
    return f"Duración: {low}-{low + NUMERIC_GROUP_SIZE - 1} h"


@dataclass(frozen=True)
class SortCriterion:
    """Un criterio de ordenación. `make_value` se llama una vez por ordenación."""

    key: str
    label: str
    reverse: bool
    make_value: Callable[[], Callable[[Game], object]]
    group_of: Callable[[object], object]
    label_group: Callable[[object], str]


#: Criterios disponibles, con las mismas claves que usa la TUI (salvo
#: `steamdb`, que la TUI no ofrece como ordenación).
CRITERIA: dict[str, SortCriterion] = {
    "title": SortCriterion(
        key="title", label="Nombre", reverse=False,
        make_value=_title_value, group_of=_name_group,
        label_group=_name_group_label,
    ),
    "user_score": SortCriterion(
        key="user_score", label="Puntuación de usuarios", reverse=True,
        make_value=_field_value("user_score"), group_of=_numeric_group,
        label_group=_score_group_label("Usuarios"),
    ),
    "critic_score": SortCriterion(
        key="critic_score", label="Puntuación de crítica", reverse=True,
        make_value=_field_value("critic_score"), group_of=_numeric_group,
        label_group=_score_group_label("Crítica"),
    ),
    # Misma fuente que la nota que se pinta en la pegatina de la caja
    # (`case_labels`), así que ordenar por esto ordena por el número que ya
    # se está viendo en el carrusel.
    "steamdb": SortCriterion(
        key="steamdb", label="Puntuación de SteamDB", reverse=True,
        make_value=_field_value("steamdb_score"), group_of=_numeric_group,
        label_group=_score_group_label("SteamDB"),
    ),
    "duration": SortCriterion(
        key="duration", label="Duración", reverse=False,
        make_value=_field_value("duration_hours"), group_of=_numeric_group,
        label_group=_duration_group_label,
    ),
}

DEFAULT_CRITERION = "title"


def scorer_criterion(label: str, scores: dict[int, float]) -> SortCriterion:
    """
    Un criterio hecho a medida para un sistema de scoring ya calculado.

    `scores` viene de `LibraryService.score`, que es quien puntúa de verdad
    (el mismo camino que usa la TUI). Aquí solo se consulta, para que ordenar
    el carrusel y la nota que se enseña salgan del mismo número.

    No entra en `CRITERIA` porque no es fijo: depende de la configuración del
    usuario y de la biblioteca, y hay que rehacerlo cada vez que se aplica.
    """
    return SortCriterion(
        key="scorer",
        label=label,
        reverse=True,
        make_value=lambda: (lambda game: scores.get(game.igdb_id)),
        group_of=_numeric_group,
        label_group=_score_group_label("Puntuación"),
    )

#: Etiqueta del grupo de los juegos sin dato, para los avisos.
NO_VALUE_GROUP = None


def order_entries(entries, criterion: SortCriterion) -> tuple[list, list]:
    """
    Ordena `entries` y devuelve `(claves_ordenadas, grupo_de_cada_una)`.

    Las dos listas van en paralelo y salen juntas a propósito: el carrusel
    necesita el orden para colocar las cajas y los grupos para saber por
    dónde cortan los saltos de L1/R1, y calcularlos por separado se
    arriesga a que dejen de cuadrar.

    Los juegos SIN dato (una nota que nadie ha puesto, una duración
    desconocida) van al final, en su propio grupo, tanto si se ordena de
    mayor a menor como al revés. Meterlos en el orden normal como si
    valieran cero los pondría los primeros al ordenar de menor a mayor, y un
    juego sin nota no es un juego malo — es un juego del que no se sabe.
    """
    value_of = criterion.make_value()

    con_valor = []
    sin_valor = []
    for entry in entries:
        value = value_of(entry.game) if entry.game is not None else None
        if value is None:
            sin_valor.append(entry)
        else:
            con_valor.append((value, entry))

    # `sort` es estable, así que los empates conservan el orden que traían
    # (alfabético, ver `real_data`): dos juegos con la misma nota salen en
    # orden de título en vez de en uno arbitrario.
    con_valor.sort(key=lambda pair: pair[0], reverse=criterion.reverse)

    keys = [entry.key for _, entry in con_valor] + [e.key for e in sin_valor]
    groups = (
        [criterion.group_of(value) for value, _ in con_valor]
        + [NO_VALUE_GROUP] * len(sin_valor)
    )
    return keys, groups


def group_label(criterion: SortCriterion, group: object) -> str:
    """Cómo se llama un grupo de cara al usuario, para el aviso del salto."""
    if group is NO_VALUE_GROUP:
        return "Sin dato"
    return criterion.label_group(group)
