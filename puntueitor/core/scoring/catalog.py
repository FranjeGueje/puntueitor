"""
Los sistemas de puntuación: qué son, cómo se explican y cómo se construyen.

Vive en `core/` por un motivo concreto. Los textos estaban escritos DOS veces
—en `gui3d/scoring_info.py` y en `tui/screens/scoring.py`— y el primero lo
documentaba como mal necesario: importar el módulo de la TUI desde el
carrusel metería Textual entero dentro de la aplicación 3D.

El diagnóstico era correcto y la solución estaba en el sitio equivocado. Estos
textos no son de Textual: son del dominio, y desde aquí los leen las dos
interfaces sin que ninguna arrastre a la otra.

Y ya habían divergido, que es lo que el propio comentario predecía: la TUI
tenía frases que el carrusel no.

`description` y `recommendation` son campos DISTINTOS, no dos versiones del
mismo texto: uno explica cómo funciona el sistema y el otro cierra diciendo
para qué sirve. Así se conserva lo que solo tenía la TUI sin volver a tener
dos copias que puedan separarse.
"""
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringSystem:
    """Un sistema de puntuación, entero."""

    #: La clave que entiende `LibraryService.score`. Se guarda en la
    #: configuración, así que cambiarla rompería los ajustes del usuario.
    key: str

    #: Nombre corto, para la lista: "Mixed Score".
    name: str

    #: Titular con su apodo: 'Mixed Score (El "Recomendador Inteligente")'.
    title: str

    #: Cómo funciona.
    description: str

    #: Para qué sirve, en una línea. Va aparte porque el carrusel pinta la
    #: descripción en un marco de tamaño fijo y no siempre cabe.
    recommendation: str

    #: Qué formulario de ajustes le toca ("weights", "hours", "genres").
    config_form: str

    #: Cómo se construye el scorer a partir de `ScoringConfig` (el de
    #: `scoring.json`, no el de las credenciales).
    build: Callable


def _mixed(config):
    from puntueitor.core.scoring.mixed_score import MixedScore

    return MixedScore(
        weight_critics=config.scoring_mixed_critics,
        weight_users=config.scoring_mixed_users,
        weight_duration=config.scoring_mixed_duration,
    )


def _weighted(config):
    from puntueitor.core.scoring.atomic.critic_score import CriticScoreScorer
    from puntueitor.core.scoring.atomic.duration_score import DurationScoreScorer
    from puntueitor.core.scoring.atomic.user_score import UserScoreScorer
    from puntueitor.core.scoring.weighted_score import WeightedScore

    return WeightedScore([
        (CriticScoreScorer(), config.scoring_weighted_critics),
        (UserScoreScorer(), config.scoring_weighted_users),
        (DurationScoreScorer(), config.scoring_weighted_duration),
    ])


def _available_time(config):
    from puntueitor.core.scoring.available_time import AvailableTimeScorer

    # Sin argumentos: las horas disponibles le llegan por el `ScoringContext`
    # en cada `score()`, no al construirlo.
    return AvailableTimeScorer()


def _genre(config):
    from puntueitor.core.scoring.atomic.genre_score import GenreScorer

    return GenreScorer()


#: En el orden en que se enseñan.
SYSTEMS: tuple[ScoringSystem, ...] = (
    ScoringSystem(
        key="mixed",
        name="Mixed Score",
        title='Mixed Score (El "Recomendador Inteligente")',
        config_form="weights",
        build=_mixed,
        description=(
            "Es un algoritmo con opinión propia, diseñado para destacar "
            "\"joyas\" que respeten tu tiempo.\n"
            "Notas: se fía más de los usuarios (50%) que de los críticos "
            "(30%). Prioriza lo que le gusta a la gente real.\n"
            "Duración: usa una curva exponencial. En lugar de restar puntos "
            "de forma constante, penaliza mucho más rápido los juegos que "
            "empiezan a ser largos. Un juego de 40h se verá mucho más "
            "castigado aquí que en el Weighted.\n"
            "Para quién es: para quien tiene mucho backlog y quiere que el "
            "sistema le recomiende lo mejor de lo mejor, dando un empujón a "
            "los juegos intensos y de duración razonable."
        ),
        recommendation=(
            "Si quieres que Puntueitor te sugiera qué jugar hoy mismo, "
            "priorizando juegos aclamados y no demasiado largos, usa Mixed."
        ),
    ),
    ScoringSystem(
        key="weighted",
        name="Weighted Score",
        title='Weighted Score (El "Equilibrado")',
        config_form="weights",
        build=_weighted,
        description=(
            "Es un promedio tradicional. Su filosofía es la previsibilidad.\n"
            "Notas: da el mismo valor a lo que dice la prensa que a lo que "
            "dicen los jugadores (40% cada uno).\n"
            "Duración: caída lineal. Hasta las 15h el juego puntúa al máximo "
            "en este apartado, y a partir de ahí va perdiendo puntos de forma "
            "constante hasta las 60h, donde la puntuación por duración es "
            "cero.\n"
            "Para quién es: para quien quiere un ranking justo y proporcional "
            "donde cada hora extra resta exactamente lo mismo."
        ),
        recommendation=(
            "Si quieres ver tu lista ordenada de forma clásica, usa Weighted."
        ),
    ),
    ScoringSystem(
        key="time",
        name="Available Time",
        title='Available Time (El "Planificador")',
        config_form="hours",
        build=_available_time,
        description=(
            "Este sistema no mira si el juego es bueno o malo, sino si encaja "
            "en tu agenda.\n"
            "Cómo funciona: toma las horas disponibles que hayas configurado "
            "(por defecto 20h) y las compara con la duración del juego.\n"
            "Resultado: los juegos que duran menos que tu tiempo disponible "
            "obtienen la mejor puntuación. Los que se pasan empiezan a recibir "
            "penalizaciones.\n"
            "Para quién es: para cuando tienes un fin de semana libre y "
            "quieres ver qué juegos podrías terminarte en ese tiempo."
        ),
        recommendation=(
            "Si tienes un rato concreto y quieres algo que quepa en él, "
            "usa Available Time."
        ),
    ),
    ScoringSystem(
        key="genre",
        name="Genre Match",
        title='Genre Match (El "Personalizador")',
        config_form="genres",
        build=_genre,
        description=(
            "El sistema más subjetivo, basado puramente en tus gustos.\n"
            "Cómo funciona: mira los géneros del juego y los compara con tus "
            "géneros preferidos.\n"
            "Resultado: sube la nota de los juegos que coinciden con lo que te "
            "gusta y hunde los que tienen géneros que no soportas.\n"
            "Para quién es: para filtrar el ruido. Si te encantan los RPG pero "
            "odias los Sports, este sistema pondrá todos tus RPG arriba del "
            "todo, tengan un 90 o un 70 de nota."
        ),
        recommendation=(
            "Si lo que quieres es ver primero lo tuyo, usa Genre Match."
        ),
    ),
)

BY_KEY: dict[str, ScoringSystem] = {sistema.key: sistema for sistema in SYSTEMS}


def get(key: str) -> ScoringSystem | None:
    """El sistema `key`, o None si no existe."""
    return BY_KEY.get(key)
