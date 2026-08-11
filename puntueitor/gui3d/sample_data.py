"""
Datos de ejemplo para validar el carrusel sin depender de la biblioteca.

Son `Game` de verdad, no dicts a medias, para que la ficha se pueda probar
igual que con datos reales — incluidos los huecos: alguno va a propósito sin
duración, sin reseñas de Steam o sin fecha, que es lo que pasa con una
biblioteca recién montada y sin enriquecer, y es justo el caso en el que la
ficha tiene que seguir cuadrando.
"""
from datetime import date

from puntueitor.core.models import Game, Stores
from puntueitor.gui3d.game_case import make_placeholder_texture

# (título, descripción, color de relleno, tiendas, géneros, horas,
#  nota usuario, nota crítica, nota SteamDB, categoría Steam,
#  reseñas positivas, reseñas negativas, fecha)
#
# Las tiendas van variadas a propósito, para poder ver el banner con uno,
# dos y tres badges sin depender de datos reales.
_SAMPLE_GAMES = (
    ("Hollow Knight", "Un metroidvania dibujado a mano ambientado en un "
     "reino de insectos en ruinas. Exploración, combate ágil y una "
     "atmósfera melancólica muy cuidada.", (0.55, 0.75, 0.35),
     (Stores.STEAM, Stores.GOG), ("Metroidvania", "Plataformas", "Aventura"),
     26.5, 92.0, 90.0, 96.32, 9, 168420, 4210, date(2017, 2, 24)),
    ("Celeste", "Plataformas de precisión sobre una montaña que es, en "
     "realidad, un viaje de superación personal. Difícil pero siempre "
     "justo.", (0.85, 0.35, 0.45), (Stores.STEAM,),
     ("Plataformas", "Indie"),
     12.0, 89.0, 94.0, 95.10, 9, 61230, 1180, date(2018, 1, 25)),
    ("Disco Elysium", "Una investigación de asesinato narrada casi "
     "enteramente a través de diálogo y de las voces en la cabeza de un "
     "detective con amnesia.", (0.75, 0.55, 0.15),
     (Stores.STEAM, Stores.EPIC, Stores.GOG), ("RPG", "Aventura"),
     33.0, 90.0, 97.0, 93.44, 8, 92110, 6890, date(2019, 10, 15)),
    ("Outer Wilds", "Un bucle temporal de 22 minutos para desentrañar los "
     "misterios de un sistema solar en miniatura. Exploración pura, sin "
     "combate.", (0.25, 0.35, 0.65), (Stores.EPIC,),
     ("Aventura", "Exploración"),
     21.0, 88.0, 92.0, None, None, None, None, date(2019, 5, 28)),
    ("Hades", "Roguelike de acción isométrica: escapa del inframundo "
     "una y otra vez mientras la historia avanza con cada intento.",
     (0.65, 0.20, 0.25), (Stores.STEAM, Stores.AMAZON),
     ("Roguelike", "Acción", "RPG"),
     45.5, 91.0, 93.0, 97.02, 9, 214880, 5120, date(2020, 9, 17)),
    ("Return of the Obra Dinn", "Reconstruye, en blanco y negro, el "
     "destino de la tripulación de un barco desaparecido usando un "
     "reloj que congela el instante de cada muerte.", (0.30, 0.30, 0.32),
     (Stores.GOG,), (),
     None, None, 89.0, None, None, None, None, None),
)


def build_sample_entries() -> tuple[list[dict], list[tuple]]:
    """
    `(entries, pending_downloads)`, con el mismo contrato que
    `real_data.build_real_entries` — aquí `pending_downloads` siempre está
    vacío porque los colores de relleno ya son la textura final, no hay nada
    que descargar.
    """
    entries = []
    for index, row in enumerate(_SAMPLE_GAMES):
        (title, description, color, stores, genres, duration, user_score,
         critic_score, steamdb, steam_review, pos, neg, released) = row

        game = Game(
            igdb_id=index,
            title=title,
            genres=genres,
            storyline=description,
            release_date=released,
            critic_score=critic_score,
            user_score=user_score,
            duration_hours=duration,
            steam_review=steam_review,
            steamdb_score=steamdb,
            review_pos=pos,
            review_neg=neg,
            stores={store: str(index) for store in stores},
        )

        entries.append({
            "key": index,
            "title": title,
            "texture": make_placeholder_texture(color),
            "stores": frozenset(stores),
            "game": game,
        })

    return entries, []
