import sys
import os
from pathlib import Path

# Añadir el directorio del proyecto al path
sys.path.append(os.getcwd())

from puntueitor.core.resolvers.hltb_resolver import HLTBResolver
from puntueitor.core.enrichers.hltb_enricher import HLTBEnricher
from puntueitor.core.models import Game, Stores
import logging

# Configurar logging para ver qué pasa internamente
logging.basicConfig(level=logging.DEBUG)

def test():
    resolver = HLTBResolver()
    enricher = HLTBEnricher(client=resolver, min_similarity=0.6)
    
    # Probar con un juego que vimos en tu lista
    test_game = Game(
        igdb_id=233,
        title='Half-Life 2',
        genres=('Shooter',),
        stores={Stores.STEAM: '220'}
    )
    
    print(f"--- Probando enriquecimiento para: {test_game.title} ---")
    enriched = enricher.enrich(test_game)
    print(f"Resultado: duration_hours = {enriched.duration_hours}")
    
    if enriched.duration_hours is None:
        print("AVISO: No se ha conseguido enriquecer el juego.")
        # Ver qué devuelve el resolver directamente
        entry = resolver.search(test_game.title)
        if entry:
            print(f"Entrada encontrada: {entry.name}, sim={entry.similarity}, story={entry.main_story}, extra={entry.main_extra}")
        else:
            print("ERROR: El resolver no encontró nada en HLTB.")
    else:
        print("ÉXITO: Se ha obtenido duración.")

if __name__ == "__main__":
    test()
