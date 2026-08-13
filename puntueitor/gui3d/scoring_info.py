"""
Los sistemas de scoring: nombre, descripción y qué se puede configurar de
cada uno.

Los textos son los mismos que enseña la TUI en `gui/screens/scoring.py`.
Están copiados y no importados a propósito: ese módulo es de Textual, e
importarlo desde aquí metería la TUI entera (y su árbol de dependencias)
dentro de la aplicación 3D solo para leer cinco cadenas. Si se retocan allí,
hay que retocarlos aquí — es el precio de que los dos frontales no se
arrastren el uno al otro.

Las CLAVES sí son las mismas ("mixed", "weighted", "time", "genre") porque
son las que entiende `LibraryService.score`, que es quien puntúa de verdad en
los dos frontales.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Scorer:
    key: str
    name: str
    title: str
    description: str
    #: Qué formulario de configuración le toca (ver `scoring_config.py`).
    config: str


#: En el mismo orden que la lista de la TUI.
SCORERS: tuple[Scorer, ...] = (
    Scorer(
        key="mixed",
        name="Mixed Score",
        title='Mixed Score (El "Recomendador Inteligente")',
        config="weights",
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
    ),
    Scorer(
        key="weighted",
        name="Weighted Score",
        title='Weighted Score (El "Equilibrado")',
        config="weights",
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
    ),
    Scorer(
        key="time",
        name="Available Time",
        title='Available Time (El "Planificador")',
        config="hours",
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
    ),
    Scorer(
        key="genre",
        name="Genre Match",
        title='Genre Match (El "Personalizador")',
        config="genres",
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
    ),
)

BY_KEY: dict[str, Scorer] = {scorer.key: scorer for scorer in SCORERS}
