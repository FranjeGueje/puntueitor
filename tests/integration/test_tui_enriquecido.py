"""
La TUI enriquece con los servicios del core, no con una copia propia.

`_enrich_worker` era una reimplementación a mano de `_enrich_loop`, y había
divergido en dos cosas que se notan:

- Le faltaba el `try/except` por juego, así que **uno que fallara se llevaba
  por delante el lote entero**. El del core lo aísla ("un juego no tumba el
  lote").
- Construía los enrichers sin `overwrite`, así que rellenaba huecos pero no
  actualizaba lo ya conocido — al revés que la acción del mismo nombre en el
  carrusel, cuyo `update_extras` lo usa a propósito.
"""
import pytest

from puntueitor.core.models import Game
from puntueitor.core.repository.library_repository import LibraryRepository
from puntueitor.core.services.library_refresh import update_extras


class EnricherQueRevienta:
    overwrite = True
    extras_cacher = None

    def __init__(self, revienta_en: str):
        self.revienta_en = revienta_en
        self.vistos = []

    def enrich(self, game):
        self.vistos.append(game.title)
        if game.title == self.revienta_en:
            raise RuntimeError("este juego revienta")
        return game


class TestUnJuegoRotoNoTumbaElLote:
    def test_the_loop_isolates_the_failure(self, monkeypatch, make_game):
        """
        El comportamiento que la TUI no tenía. Se prueba sobre el servicio
        del core, que es a quien delega ahora.
        """
        from puntueitor.core.enrichers import factory

        juegos = [make_game(igdb_id=i, title=t)
                  for i, t in enumerate(("Uno", "Malo", "Tres"), start=1)]

        repo = LibraryRepository()
        monkeypatch.setattr(type(repo), "load", lambda self: juegos)
        monkeypatch.setattr(repo, "save_game", lambda game: None)

        roto = EnricherQueRevienta("Malo")
        # Al módulo de la fábrica, no al de `library_refresh`: este la
        # importa DENTRO de la función, así que es ahí donde la busca.
        monkeypatch.setattr(factory, "build_enrichers", lambda *a, **k: [roto])

        vistos = []
        update_extras(repo, on_progress=lambda a, b, t: vistos.append(t))

        assert vistos == ["Uno", "Malo", "Tres"], (
            "el juego que revienta no puede parar el recorrido"
        )


class TestLaTuiDelegaEnElCore:
    """
    Se comprueba leyendo el código: montar la TUI entera para esto exigiría
    una terminal y un hilo, y lo que importa es a QUIÉN llama.
    """

    @staticmethod
    def _worker() -> str:
        from pathlib import Path

        raiz = Path(__file__).resolve().parent.parent.parent
        texto = (raiz / "puntueitor" / "tui" / "app.py").read_text()
        inicio = texto.index("    def _enrich_worker(self):")
        fin = texto.index("    def _on_game_enriched")
        return texto[inicio:fin]

    def test_it_calls_the_core_services(self):
        worker = self._worker()

        assert "update_extras" in worker
        assert "enrich_all" in worker

    def test_it_does_not_walk_the_library_itself(self):
        """Si vuelve a recorrerla, vuelve a tener su propia copia del bucle."""
        worker = self._worker()

        assert "for " not in worker, "el recorrido es del core"
        assert "build_enrichers" not in worker

    def test_cancelling_goes_through_should_stop(self):
        worker = self._worker()

        assert "should_stop" in worker
        assert "is_enriching" in worker

    def test_it_no_longer_saves_by_hand(self):
        """
        El servicio guarda juego a juego; hacerlo también en la interfaz era
        escribir dos veces cada fila.
        """
        from pathlib import Path

        raiz = Path(__file__).resolve().parent.parent.parent
        texto = (raiz / "puntueitor" / "tui" / "app.py").read_text()
        inicio = texto.index("    def _on_game_enriched")
        fin = texto.index("    def ", inicio + 10)

        assert "save_game" not in texto[inicio:fin]
