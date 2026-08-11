import logging

from puntueitor.core.cachers.base_cacher import BaseCacher

logger = logging.getLogger(__name__)

_UPSERT_EXTRAS = """
    INSERT INTO extras (
        id_igdb, duration_hours, steam_review, steamdb_score,
        review_pos, review_neg
    )
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(id_igdb) DO UPDATE SET
        duration_hours=COALESCE(excluded.duration_hours, extras.duration_hours),
        steam_review=COALESCE(excluded.steam_review, extras.steam_review),
        steamdb_score=COALESCE(excluded.steamdb_score, extras.steamdb_score),
        review_pos=COALESCE(excluded.review_pos, extras.review_pos),
        review_neg=COALESCE(excluded.review_neg, extras.review_neg)
"""


class ExtrasCacher(BaseCacher):
    """
    Métricas enriquecidas (duración HLTB, valoraciones de Steam).

    `duration_hours` NULL significa "duración desconocida". El flag
    `hltb_checked` registra aparte que ya se consultó HLTB y no encontró nada,
    para no repetir la búsqueda en cada arranque. Antes ambos significados se
    apilaban sobre el valor 0, lo que hacía que un juego sin duración conocida
    puntuase como si durase cero horas.
    """

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS extras (
            id_igdb INTEGER PRIMARY KEY,
            duration_hours REAL,
            steam_review INTEGER,
            steamdb_score REAL,
            review_pos INTEGER,
            review_neg INTEGER,
            hltb_checked INTEGER NOT NULL DEFAULT 0
        );
    """

    MIGRATIONS = (
        "ALTER TABLE extras ADD COLUMN steam_review INTEGER",
        "ALTER TABLE extras ADD COLUMN steamdb_score REAL",
        "ALTER TABLE extras ADD COLUMN review_pos INTEGER",
        "ALTER TABLE extras ADD COLUMN review_neg INTEGER",
        "ALTER TABLE extras ADD COLUMN hltb_checked INTEGER NOT NULL DEFAULT 0",
        # Reinterpreta el antiguo centinela: duration_hours = 0 significaba
        # "HLTB no encontró nada", no "dura cero horas". Idempotente.
        "UPDATE extras SET duration_hours = NULL, hltb_checked = 1"
        " WHERE duration_hours = 0",
    )

    def get_all_extras(self) -> dict[int, dict]:
        return {
            row["id_igdb"]: dict(row)
            for row in self._query("SELECT * FROM extras")
        }

    def get_extras(self, igdb_id: int) -> dict:
        rows = self._query("SELECT * FROM extras WHERE id_igdb = ?", (igdb_id,))
        return dict(rows[0]) if rows else {}

    def save_extras(
        self,
        igdb_id: int,
        duration_hours: float | None = None,
        steam_review: int | None = None,
        steamdb_score: float | None = None,
        review_pos: int | None = None,
        review_neg: int | None = None,
    ) -> None:
        self._write(_UPSERT_EXTRAS, (
            igdb_id, duration_hours, steam_review,
            steamdb_score, review_pos, review_neg,
        ))

    def save_extras_bulk(self, rows: list[tuple]) -> None:
        """
        Guarda muchos extras en una sola transacción.

        `rows` son tuplas
        (igdb_id, duration_hours, steam_review, steamdb_score, review_pos, review_neg).
        """
        if rows:
            self._write_many(_UPSERT_EXTRAS, rows)

    # ──────────────────────────────
    # Estado de consulta a HLTB
    # ──────────────────────────────

    def is_hltb_checked(self, igdb_id: int) -> bool:
        rows = self._query(
            "SELECT hltb_checked FROM extras WHERE id_igdb = ?", (igdb_id,)
        )
        return bool(rows and rows[0]["hltb_checked"])

    def get_hltb_checked_ids(self) -> set[int]:
        """IDs ya consultados en HLTB sin resultado, para evitar reintentos."""
        return {
            row["id_igdb"]
            for row in self._query(
                "SELECT id_igdb FROM extras WHERE hltb_checked = 1"
            )
        }

    def mark_hltb_checked(self, igdb_id: int) -> None:
        self._write(
            "INSERT INTO extras (id_igdb, hltb_checked) VALUES (?, 1)"
            " ON CONFLICT(id_igdb) DO UPDATE SET hltb_checked = 1",
            (igdb_id,),
        )

    def clear_all(self) -> None:
        self._write("DELETE FROM extras")
