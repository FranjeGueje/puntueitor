"""
El contenido de los menús del carrusel: qué filas trae cada uno y con qué
claves, que son el contrato con `gui3d/app.py`.

No hace falta ventana: `MenuItem` es un dataclass y `menus.py` solo describe,
no dibuja.
"""
from puntueitor.gui3d import menus


class TestGameMenu:
    def test_sections_and_order(self, sample_game):
        keys = [item.key for item in menus.build_game_items(sample_game)]
        assert keys == [
            "sec_flags",
            "flag:finished", "flag:hidden", "flag:backlog", "flag:favorite",
            "sec_advanced",
            menus.ENRICH_KEY, menus.FORGET_KEY,
        ]

    def test_headers_are_not_focusable(self, sample_game):
        items = menus.build_game_items(sample_game)
        headers = [i for i in items if i.kind == "header"]
        assert [i.label for i in headers] == ["ESTADOS", "AVANZADO"]
        assert not any(i.focusable for i in headers)

    def test_checkboxes_reflect_the_game(self, make_game):
        game = make_game(finished=True, favorite=True)
        checked = {
            i.payload["field"]: i.checked
            for i in menus.build_game_items(game) if i.kind == "check"
        }
        assert checked == {
            "finished": True, "hidden": False, "backlog": False, "favorite": True,
        }

    def test_actions_are_plain_rows(self, sample_game):
        """
        Ni casillas ni valores: `_on_confirm` manda las casillas a
        `_on_game_flag_toggled` y solo las filas normales llegan a
        `_activate`, que es donde se manejan estas dos.
        """
        actions = [
            i for i in menus.build_game_items(sample_game)
            if i.key in (menus.ENRICH_KEY, menus.FORGET_KEY)
        ]
        assert [i.label for i in actions] == ["Enriquecer", "Desconocer"]
        assert all(i.kind == "action" and i.value is None for i in actions)


class TestConfirmMenu:
    def test_question_lines_become_headers(self):
        items = menus.build_confirm_items(("una", "dos"), "Sí, vale")
        headers = [i.label for i in items if i.kind == "header"]
        # Las dos líneas de la pregunta, más el separador vacío.
        assert headers == ["una", "dos", ""]

    def test_no_comes_first_and_yes_last(self):
        items = menus.build_confirm_items(("¿seguro?",), "Sí, vale")
        assert [i.key for i in items if i.focusable] == [
            menus.CONFIRM_NO_KEY, menus.CONFIRM_YES_KEY,
        ]

    def test_default_focus_is_the_safe_option(self):
        """
        `Menu.set_items` deja el foco en la primera fila enfocable, así que
        la opción marcada de serie tiene que ser la que no hace nada.
        """
        items = menus.build_confirm_items(("¿seguro?",), "Sí, borrar")
        first = next(i for i in items if i.focusable)
        assert first.key == menus.CONFIRM_NO_KEY
        assert first.label == "No, cancelar"

    def test_both_actions_have_their_texts(self):
        for question, yes in (
            (menus.ENRICH_QUESTION, menus.ENRICH_YES),
            (menus.FORGET_QUESTION, menus.FORGET_YES),
        ):
            assert len(question) >= 1
            assert all(line.strip() for line in question)
            assert yes.startswith("Sí,")


class FakeResult:
    """Lo justo que `build_search_result_items` mira de un `SearchResult`."""

    def __init__(self, igdb_id, title, year):
        self.igdb_id, self.title, self.year = igdb_id, title, year


class TestUnknownMenus:
    def test_two_ways_to_identify(self):
        items = menus.build_unknown_items(object())
        assert [i.key for i in items] == [
            menus.UNKNOWN_TITLE_KEY, menus.UNKNOWN_STORE_KEY,
        ]
        # Las mismas que la TUI y en el mismo orden.
        assert [i.label for i in items] == [
            "Buscar por título", "Volver a buscar por tienda",
        ]

    def test_results_show_the_year_apart(self):
        items = menus.build_search_result_items([
            FakeResult(1, "Doom", 1993), FakeResult(2, "Doom", None),
        ])
        assert [i.display_label() for i in items] == [
            "Doom  <1993>", "Doom  <—>",
        ]

    def test_result_carries_itself_in_the_payload(self):
        result = FakeResult(42, "Doom", 1993)
        item = menus.build_search_result_items([result])[0]
        assert item.payload["result"] is result
        assert item.key.startswith(menus.UNKNOWN_RESULT_PREFIX)

    def test_results_fit_without_scrolling(self):
        """La búsqueda pide 15 y el menú enseña 16 filas de una vez."""
        from puntueitor.core.services.unknown_actions import SEARCH_LIMIT
        from puntueitor.gui3d.menu import MAX_VISIBLE_ITEMS
        assert SEARCH_LIMIT <= MAX_VISIBLE_ITEMS


class TestEditorRapido:
    """
    La tabla de gestos del Editor Rápido.

    Es lo único del modo que se puede probar sin abrir una ventana, y es
    justo donde un despiste no se nota al leer el código: invertir arriba y
    abajo marcaría como terminado lo que querías dejar pendiente, y encima
    lo escribiría en la base de datos.
    """

    def test_it_covers_exactly_the_four_flags(self):
        """
        Ni uno menos (un estado inalcanzable desde el editor) ni uno más (una
        dirección que escribe un campo que no existe). Si mañana se añade un
        estado a `GAME_FLAGS`, este test avisa de que hay que decidir si entra.
        """
        campos = set(menus.EDITOR_FLAGS.values())
        assert campos == {campo for campo, _ in menus.GAME_FLAGS}

    def test_no_field_is_repeated(self):
        assert len(set(menus.EDITOR_FLAGS.values())) == len(menus.EDITOR_FLAGS)

    def test_the_four_directions_are_perpendicular(self):
        """
        Nada de diagonales: el mando devuelve un solo eje a propósito, y una
        entrada diagonal en la tabla sería inalcanzable.
        """
        for x, y in menus.EDITOR_FLAGS:
            assert (x, y) != (0, 0)
            assert x == 0 or y == 0
            assert abs(x) <= 1 and abs(y) <= 1

    def test_down_is_finished_and_up_is_backlog(self):
        """Lo pedido, y lo que un despiste invertiría. +1 es ABAJO."""
        assert menus.EDITOR_FLAGS[(0, 1)] == "finished"
        assert menus.EDITOR_FLAGS[(0, -1)] == "backlog"
        assert menus.EDITOR_FLAGS[(-1, 0)] == "hidden"
        assert menus.EDITOR_FLAGS[(1, 0)] == "favorite"

    def test_the_keys_match_the_stick(self):
        """
        Teclado y mando no pueden divergir: las teclas apuntan a las MISMAS
        direcciones, así que basta con mirar una tabla para saber las dos.
        """
        assert set(menus.EDITOR_KEYS.values()) == set(menus.EDITOR_FLAGS)
        assert menus.EDITOR_KEYS["k"] == (0, 1)   # terminado, como abajo
        assert menus.EDITOR_KEYS["i"] == (0, -1)  # pendiente, como arriba

    def test_the_keys_are_not_arrows(self):
        """Las flechas siguen navegando: sin eso el modo no sería rápido."""
        assert not any(
            tecla.startswith("arrow") for tecla in menus.EDITOR_KEYS
        )

    def test_every_flag_has_a_name_to_announce(self):
        for campo in menus.EDITOR_FLAGS.values():
            assert menus.EDITOR_LABELS.get(campo)

    def test_the_notice_says_which_way_it_went(self):
        assert menus.editor_notice("finished", True) != menus.editor_notice(
            "finished", False
        )
        assert "Terminado" in menus.editor_notice("finished", True)

    def test_the_blocked_message_says_how_to_get_out(self):
        aviso = menus.EDITOR_BLOCKED.format(gesto="Filtrar")
        assert "Filtrar" in aviso
        assert "Editor" in aviso


class TestAdvancedMenu:
    def test_between_puntueitor3d_and_quit(self):
        keys = [i.key for i in menus.OPTIONS_ITEMS]
        assert keys == ["config", "gui3d", "advanced", "quit"]

    def test_the_heavy_operations(self):
        """
        Dos secciones: las tres de rehacer datos —de menos a más destructiva,
        con la que no borra nada primero— y las dos de la copia.
        """
        items = menus.ADVANCED_ITEMS
        assert [i.label for i in items] == [
            "DATOS",
            "Enriquecer todo",
            "Enriquecer todo DESTRUCTIVO",
            "Restaurar Puntueitor MUY DESTRUCTIVO",
            "COPIA DE SEGURIDAD",
            "Copia de seguridad",
            "Restaurar copia",
        ]

    def test_only_the_actions_take_focus(self):
        """
        Las cabeceras son títulos, no opciones: si recibieran foco, el mando
        se pararía en ellas y "elegir" no haría nada.
        """
        enfocables = [i.key for i in menus.ADVANCED_ITEMS if i.focusable]
        assert enfocables == [
            menus.UPDATE_EXTRAS_KEY, menus.ENRICH_ALL_KEY, menus.REGENERATE_KEY,
            menus.BACKUP_KEY, menus.RESTORE_KEY,
        ]

    def test_restore_warns_about_what_it_overwrites(self):
        aviso = " ".join(menus.RESTORE_WARNING).lower()
        assert "sobrescribir" in aviso
        # Que se cierra hay que decirlo: si no, parece que no ha pasado nada.
        assert "cerrará" in " ".join(menus.RESTORE_NOTE)

    def test_the_destructive_one_is_marked_as_such(self):
        """
        Las dos se llaman igual; lo único que las separa de un vistazo es esa
        palabra, así que si desaparece la etiqueta miente.
        """
        destructiva = next(
            i for i in menus.ADVANCED_ITEMS if i.key == menus.ENRICH_ALL_KEY
        )
        assert "DESTRUCTIVO" in destructiva.label

    def test_update_extras_promises_not_to_delete(self):
        aviso = " ".join(menus.UPDATE_EXTRAS_NOTE).lower()
        assert "no se borra nada" in aviso
        assert "minutos" in aviso

    def test_regenerate_warning_says_what_is_lost(self):
        aviso = " ".join(menus.REGENERATE_WARNING).lower()
        assert "borrar" in aviso
        assert "perderás" in aviso
        assert "minutos" in " ".join(menus.REGENERATE_NOTE).lower()

    def test_warning_lines_are_painted(self):
        from puntueitor.gui3d.menu import WARNING_COLOR
        items = menus.build_confirm_items(
            menus.REGENERATE_WARNING + menus.REGENERATE_NOTE,
            menus.REGENERATE_YES,
            warning=len(menus.REGENERATE_WARNING),
        )
        coloreadas = [i.label for i in items if i.color == WARNING_COLOR]
        assert coloreadas == list(menus.REGENERATE_WARNING)
        # Y ninguna fila enfocable lleva color: `Menu._refresh_focus` lo
        # machacaría al mover el foco.
        assert not any(i.color for i in items if i.focusable)

    def test_no_warning_by_default(self):
        items = menus.build_confirm_items(("¿seguro?",), "Sí")
        assert not any(i.color for i in items)
