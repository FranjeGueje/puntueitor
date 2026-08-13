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
