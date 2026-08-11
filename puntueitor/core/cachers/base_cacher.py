import logging
import sqlite3
import threading
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DB = Path.home() / ".cache" / "puntueitor" / "puntueitor.db"

#: sqlite3 acepta parámetros posicionales (?) o con nombre (:campo).
Params = Sequence | Mapping[str, object]


class BaseCacher:
    """
    Base común de los cachers SQLite.

    Aporta tres cosas que antes estaban copiadas (y divergían) en cada cacher:

    1. Una conexión por hilo, en vez de abrir una nueva en cada llamada.
       `with sqlite3.connect(...)` solo hace commit/rollback — no cierra —, así
       que el patrón anterior dejaba conexiones vivas y pagaba el coste de
       apertura en cada operación.
    2. El esquema declarado una sola vez en `SCHEMA`, más migraciones
       best-effort en `MIGRATIONS` para bases de datos ya existentes.
    3. Manejo de errores uniforme: un fallo puntual se registra y degrada con
       gracia, pero NO desactiva la caché para el resto de la sesión. Solo un
       fallo de inicialización marca el cacher como no disponible.
    """

    #: Ruta por defecto de la base de datos. Las subclases la sobreescriben.
    DEFAULT_PATH: Path = CACHE_DB

    #: DDL idempotente, ejecutado con `executescript` al inicializar.
    SCHEMA: str = ""

    #: Sentencias best-effort para migrar bases antiguas. Fallan si ya se
    #: aplicaron, y eso es esperado.
    MIGRATIONS: tuple[str, ...] = ()

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else self.DEFAULT_PATH
        self._local = threading.local()
        self._available = False

        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._connect()
            if self.SCHEMA:
                conn.executescript(self.SCHEMA)
            self._apply_migrations(conn)
            conn.commit()
            self._available = True
        except Exception as e:
            logger.warning(
                f"Failed to initialize {type(self).__name__} at {self.db_path}: {e}"
            )

    # ──────────────────────────────
    # Conexión
    # ──────────────────────────────

    @property
    def available(self) -> bool:
        """True si el cacher se inicializó correctamente."""
        return self._available

    def _connect(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # WAL permite lecturas concurrentes mientras los enrichers escriben
            # desde el ThreadPoolExecutor; busy_timeout evita "database is
            # locked" inmediato bajo contención.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        for statement in self.MIGRATIONS:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                # Ya aplicada (columna duplicada). Es el caso normal.
                pass

    # ──────────────────────────────
    # Helpers de ejecución
    # ──────────────────────────────

    def _query(self, sql: str, params: Params = ()) -> list[sqlite3.Row]:
        """SELECT que degrada a lista vacía si algo falla."""
        if not self._available:
            return []
        try:
            return self._connect().execute(sql, params).fetchall()
        except Exception as e:
            logger.warning(f"{type(self).__name__}: query failed: {e}")
            return []

    def _write(self, sql: str, params: Params = ()) -> bool:
        """INSERT/UPDATE/DELETE. Devuelve True si se aplicó."""
        if not self._available:
            return False
        try:
            conn = self._connect()
            with conn:
                conn.execute(sql, params)
            return True
        except Exception as e:
            logger.warning(f"{type(self).__name__}: write failed: {e}")
            return False

    def _write_many(self, sql: str, rows: Iterable) -> bool:
        """Escritura por lotes en una sola transacción."""
        if not self._available:
            return False
        try:
            conn = self._connect()
            with conn:
                conn.executemany(sql, rows)
            return True
        except Exception as e:
            logger.warning(f"{type(self).__name__}: bulk write failed: {e}")
            return False
