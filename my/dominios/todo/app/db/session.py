"""Acceso a la base de datos: SQLAlchemy SINCRÓNICO.

Sincrónico porque el servidor gRPC es sincrónico (decisión D2). Mezclar un `Session`
sync dentro de un handler async bloquea el event loop; mezclar un `AsyncSession` en un
handler sync obliga a envolver cada consulta en `asyncio.run()`. La capa de acceso a
datos es lo que hace que la elección sea transversal y no por caso de uso.

Soporta Postgres y SQLite cambiando solo `DATABASE_URL`:

    postgresql://dev:dev@localhost:5432/plataforma   producción y dev con docker
    sqlite:///./dominio.db                            dev local sin docker
    sqlite:///:memory:                                tests

SQLite es SOLO para tests y desarrollo — ver la advertencia al final del archivo.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


def _is_memory(url: str) -> bool:
    return ":memory:" in url or "mode=memory" in url


def _engine_kwargs(url: str) -> dict:
    """Argumentos de create_engine según el motor.

    SQLite NO acepta `pool_size` ni `max_overflow`: su pool por defecto es
    `SingletonThreadPool` (archivo) o `NullPool`, y pasarle esos argumentos lanza
    `TypeError: Invalid argument(s) sent to create_engine()`. Por eso la bifurcación
    existe y no es cosmética.
    """
    if url.startswith("sqlite"):
        kwargs: dict = {
            # El servidor gRPC atiende cada RPC en un hilo del pool, y SQLite por
            # defecto prohíbe usar una conexión desde otro hilo del que la creó.
            "connect_args": {"check_same_thread": False},
        }
        if _is_memory(url):
            # Sin StaticPool, CADA conexión abre una base en memoria distinta y vacía:
            # las tablas que creó el fixture no existen para el resto del test, y el
            # error que sale es "no such table", que no señala la causa.
            kwargs["poolclass"] = StaticPool
        return kwargs

    # Postgres. La invariante de conexiones está en config.py y en 04-base-de-datos.md:
    #     GRPC_MAX_WORKERS <= DB_POOL_SIZE + DB_MAX_OVERFLOW
    # y con una sola instancia el presupuesto es COMPARTIDO entre todos los dominios:
    #     permanentes = Σ (dominios × DB_POOL_SIZE)
    return {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_pre_ping": True,
    }


class Database:
    def __init__(self, url: str) -> None:
        self._url = url
        self._engine = create_engine(url, future=True, **_engine_kwargs(url))
        self._session_factory = sessionmaker(
            bind=self._engine, autoflush=False, expire_on_commit=False,
        )

    @property
    def engine(self):
        return self._engine

    @property
    def is_sqlite(self) -> bool:
        """Para el código que tenga que ramificar por motor. Usar lo menos posible:
        cada rama es una diferencia entre lo que se testea y lo que corre en producción."""
        return self._url.startswith("sqlite")

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Una transacción por unidad de trabajo. Commit al salir bien, rollback al fallar."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
