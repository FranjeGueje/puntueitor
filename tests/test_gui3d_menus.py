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


class TestCreditos:
    """
    La pantalla de créditos.

    Lo que se comprueba no es la redacción sino lo que la licencia OBLIGA a
    que esté (los iconos de Flaticon piden atribución) y lo que hace que se
    pueda leer entera.
    """

    def test_it_is_in_the_options_menu(self):
        keys = [i.key for i in menus.OPTIONS_ITEMS]
        assert keys == ["accounts", "config", "gui3d", "advanced", "credits", "quit"]

    def test_it_fits_on_one_screen(self):
        """
        La condición de la que depende todo: el menú centra su ventana
        visible en el elemento con foco, y aquí solo hay uno, el último. Si
        la lista pasara de `MAX_VISIBLE_ITEMS`, las primeras líneas quedarían
        fuera y no habría forma de llegar a ellas.
        """
        from puntueitor.gui3d.menu import MAX_VISIBLE_ITEMS
        assert len(menus.build_credits_items()) <= MAX_VISIBLE_ITEMS

    def test_only_the_back_item_takes_focus(self):
        items = menus.build_credits_items()
        enfocables = [i.key for i in items if i.focusable]
        assert enfocables == [menus.CREDITS_BACK_KEY]
        assert items[-1].key == menus.CREDITS_BACK_KEY

    def test_it_credits_the_icon_authors(self):
        """
        Los cuatro de Flaticon, que es lo que exige su licencia. Estaban solo
        en `assets/labels/creditos.txt`, donde no los ve quien usa la
        aplicación.
        """
        texto = " ".join(i.label for i in menus.build_credits_items())
        for autor in ("alien.studio", "vectorsmarket15", "Stellalunart",
                      "Design Circle"):
            assert autor in texto

    def test_it_credits_the_fonts_with_their_licence(self):
        texto = " ".join(i.label for i in menus.build_credits_items())
        assert "Robert Jablonski" in texto   # Hussar Print A
        assert "Yukari Hafner" in texto      # PromptFont
        assert "OFL" in texto

    def test_it_credits_the_author_and_the_licence(self):
        texto = " ".join(i.label for i in menus.build_credits_items())
        assert "FranjeGueje" in texto
        assert "MIT" in texto

    def test_the_version_is_not_hardcoded(self):
        """Para no tener que tocar esto en cada release."""
        from puntueitor import __version__
        texto = " ".join(i.label for i in menus.build_credits_items())
        assert __version__ in texto

    def test_it_credits_where_the_data_comes_from(self):
        texto = " ".join(i.label for i in menus.build_credits_items())
        for fuente in ("IGDB", "HowLongToBeat", "Steam"):
            assert fuente in texto

    def test_it_credits_the_projects_that_documented_the_store_apis(self):
        """
        Las APIs de GOG, Epic y Amazon no las documentan sus dueños: están
        aquí porque legendary, gogdl y nile las averiguaron y lo publicaron.
        No usamos su código —su licencia no obliga a nada— y aun así se les
        nombra, porque sin ellos tres de las cuatro tiendas no funcionarían.
        """
        texto = " ".join(i.label for i in menus.build_credits_items())
        for proyecto in ("legendary", "gogdl", "nile"):
            assert proyecto in texto

    def test_heroic_is_no_longer_credited(self):
        """Ya no se lee nada suyo: acreditarlo sería mentir sobre la fuente."""
        texto = " ".join(i.label for i in menus.build_credits_items())
        assert "Heroic" not in texto


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
    def test_between_puntueitor3d_and_credits(self):
        keys = [i.key for i in menus.OPTIONS_ITEMS]
        assert keys.index("advanced") == keys.index("gui3d") + 1
        assert keys[-1] == "quit"

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


class TestMenuOpciones:
    def test_accounts_comes_first(self):
        """
        Es lo primero que hay que hacer: sin credenciales ni sesiones no se
        carga ninguna biblioteca, y todo lo demás del menú opera sobre juegos
        que todavía no existen.
        """
        keys = [i.key for i in menus.OPTIONS_ITEMS]
        assert keys[0] == "accounts"
        assert keys.index("accounts") < keys.index("config")


class TestMenuCuentas:
    """
    El menú de Cuentas: con qué te identificas ante cada servicio.

    Se prueban las CLAVES, no el aspecto: son el contrato con `_activate` de
    `gui3d/app.py`, y ya pasó que el menú pintaba las filas bien pero el
    despacho solo miraba las que empiezan por `set:`. Elegir una tienda no
    abría nada y el fallo solo se veía como una línea suelta en el log.
    """

    @staticmethod
    def _items(values=None, sessions=None):
        return menus.build_accounts_items(values or {}, sessions)

    @staticmethod
    def _cuentas(values=None, sessions=None):
        return [
            item for item in menus.build_accounts_items(values or {}, sessions)
            if item.key.startswith("login:")
        ]

    def test_it_has_the_credentials_and_the_stores(self):
        cabeceras = [i.label for i in self._items() if i.kind == "header"]
        assert "IGDB" in cabeceras
        assert "STEAM" in cabeceras
        assert "TIENDAS" in cabeceras

    def test_the_credentials_are_text_fields(self):
        claves = [i.key for i in self._items()]
        for campo in ("igdb_client_id", "igdb_client_secret",
                      "steam_user_id", "steam_api_key"):
            assert f"set:{campo}" in claves

    def test_steam_has_no_connect_row(self):
        """
        Steam no tiene OAuth para terceros: entrar por el navegador no
        ahorraría poner la API key a mano, solo lo aparentaría.
        """
        assert "login:steam" not in [i.key for i in self._items()]

    def test_there_is_one_row_per_store_with_a_session(self):
        assert [i.key for i in self._cuentas()] == [
            "login:gog", "login:epic", "login:amazon",
        ]

    def test_the_prefix_is_the_one_the_dispatcher_routes(self):
        """
        `app._activate` enruta por prefijo (`set:` y `login:`). Si alguien
        renombra estas claves sin tocar allí, las filas dejan de hacer nada
        sin que falle nada.
        """
        for item in self._cuentas():
            assert item.key.startswith(("set:", "login:"))

    def test_the_state_of_each_store_is_shown(self):
        estados = {
            i.key: i.value
            for i in self._cuentas(sessions={"gog": True, "epic": False})
        }
        assert estados["login:gog"] == "Iniciada"
        assert estados["login:epic"] == "Sin sesión"

    def test_without_state_they_all_show_as_logged_out(self):
        assert all(i.value == "Sin sesión" for i in self._cuentas())

    def test_they_are_plain_rows_not_checkboxes(self):
        """
        Una casilla iría a `_toggle_setting_store` y no abriría el navegador:
        `_on_confirm` desvía las de tipo `check` antes de llegar a `_activate`.
        """
        assert all(i.kind not in ("check", "cycle") for i in self._cuentas())

    def test_they_carry_the_store_in_the_payload(self):
        assert [i.payload["store"] for i in self._cuentas()] == [
            "gog", "epic", "amazon",
        ]

    def test_it_can_be_saved(self):
        assert "set:save" in [i.key for i in self._items()]


class TestMenuConfiguracion:
    """Lo que queda tras llevarse las credenciales a Cuentas."""

    def test_it_only_has_the_stores_to_load(self):
        items = menus.build_settings_items({})
        casillas = [i.payload["field"] for i in items if i.kind == "check"]
        assert casillas == [campo for campo, _ in menus.SETTINGS_STORES]

    def test_the_credentials_are_no_longer_here(self):
        claves = [i.key for i in menus.build_settings_items({})]
        for campo in ("igdb_client_secret", "steam_api_key", "steam_user_id"):
            assert f"set:{campo}" not in claves

    def test_no_store_logins_here_either(self):
        claves = [i.key for i in menus.build_settings_items({})]
        assert not any(k.startswith("login:") for k in claves)


class TestSettingsDispatch:
    """
    Que elegir una fila de CUENTAS llegue de verdad al módulo `accounts_ui`.

    `_activate` es un despachador puro sobre la clave, así que se le puede
    llamar sin ventana pasándole un objeto de mentira por `self`. Este es el
    test que faltaba: los de arriba comprobaban que el menú pintaba las filas
    bien, y aun así elegirlas no hacía nada porque el despacho no las miraba.

    Desde que Cuentas y Tiendas salieron a `gui3d/accounts_ui.py`, `_activate`
    ya no llama a un método de `self`: llama a una función del módulo. Se
    parchea ahí, no en la app de mentira.
    """

    class AppFalsa:
        pass

    @staticmethod
    def _elegir(key, monkeypatch):
        from puntueitor.gui3d import accounts_ui, app as app_module

        recibidas = []
        monkeypatch.setattr(
            accounts_ui, "activate_setting",
            lambda app, k: recibidas.append(k),
        )
        app_module.App._activate(
            TestSettingsDispatch.AppFalsa(), menu=None, key=key,
        )
        return recibidas

    def test_choosing_a_store_reaches_the_login(self, monkeypatch):
        assert self._elegir("login:gog", monkeypatch) == ["login:gog"]

    def test_the_text_fields_still_work(self, monkeypatch):
        assert self._elegir("set:steam_api_key", monkeypatch) == ["set:steam_api_key"]

    def test_every_account_row_is_routed(self, monkeypatch):
        for store, _ in menus.SETTINGS_ACCOUNTS:
            assert self._elegir(f"login:{store}", monkeypatch) == [f"login:{store}"]

    @staticmethod
    def _abrir(key, monkeypatch):
        from puntueitor.gui3d import accounts_ui, app as app_module

        abiertos = []
        monkeypatch.setattr(
            accounts_ui, "open_accounts_menu", lambda app: abiertos.append("accounts"),
        )
        monkeypatch.setattr(
            accounts_ui, "open_settings_menu", lambda app: abiertos.append("config"),
        )
        app_module.App._activate(
            TestSettingsDispatch.AppFalsa(), menu=None, key=key,
        )
        return abiertos

    def test_the_two_option_entries_open_their_own_menu(self, monkeypatch):
        """
        Son dos menús distintos sobre la misma configuración. Si "accounts"
        no estuviera enrutado, elegirlo no haría nada visible — que es
        exactamente lo que pasó con las filas de CUENTAS.
        """
        assert self._abrir("accounts", monkeypatch) == ["accounts"]
        assert self._abrir("config", monkeypatch) == ["config"]
