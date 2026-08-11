"""Datos de ejemplo para validar el carrusel sin depender de LibraryService."""
from puntueitor.core.models import Stores
from puntueitor.gui3d.game_case import make_placeholder_texture

# (título, descripción, color RGB de la carátula de relleno, tiendas donde
# está disponible — variado a propósito para poder ver el banner de tiendas
# con 1, 2 y 3 badges sin depender de datos reales)
_SAMPLE_GAMES = (
    ("Hollow Knight", "Un metroidvania dibujado a mano ambientado en un "
     "reino de insectos en ruinas. Exploración, combate ágil y una "
     "atmósfera melancólica muy cuidada.", (0.55, 0.75, 0.35),
     (Stores.STEAM, Stores.GOG)),
    ("Celeste", "Plataformas de precisión sobre una montaña que es, en "
     "realidad, un viaje de superación personal. Difícil pero siempre "
     "justo.", (0.85, 0.35, 0.45), (Stores.STEAM,)),
    ("Disco Elysium", "Una investigación de asesinato narrada casi "
     "enteramente a través de diálogo y de las voces en la cabeza de un "
     "detective con amnesia.", (0.75, 0.55, 0.15),
     (Stores.STEAM, Stores.EPIC, Stores.GOG)),
    ("Outer Wilds", "Un bucle temporal de 22 minutos para desentrañar los "
     "misterios de un sistema solar en miniatura. Exploración pura, sin "
     "combate.", (0.25, 0.35, 0.65), (Stores.EPIC,)),
    ("Hades", "Roguelike de acción isométrica: escapa del inframundo "
     "una y otra vez mientras la historia avanza con cada intento.",
     (0.65, 0.20, 0.25), (Stores.STEAM, Stores.AMAZON)),
    ("Return of the Obra Dinn", "Reconstruye, en blanco y negro, el "
     "destino de la tripulación de un barco desaparecido usando un "
     "reloj que congela el instante de cada muerte.", (0.30, 0.30, 0.32),
     (Stores.GOG,)),
)


def build_sample_entries() -> tuple[list[dict], list[tuple]]:
    """
    `(entries, pending_downloads)`, con el mismo contrato que
    `real_data.build_real_entries` — aquí `pending_downloads` siempre está
    vacío porque los colores de relleno ya son la textura final, no hay nada
    que descargar.
    """
    entries = [
        {
            "key": index,
            "title": title,
            "description": description,
            "texture": make_placeholder_texture(color),
            "stores": frozenset(stores),
        }
        for index, (title, description, color, stores) in enumerate(_SAMPLE_GAMES)
    ]
    return entries, []
