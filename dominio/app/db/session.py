"""Acceso a la base de datos: SQLAlchemy SINCRÓNICO.

Sincrónico porque el servidor gRPC es sincrónico (decisión D2). Mezclar un `Session`
sync dentro de un handler async bloquea el event loop; mezclar un `AsyncSession` en un
handler sync obliga a envolver cada consulta en `asyncio.run()`. La capa de acceso a
datos es lo que hace que la elección sea transversal y no por caso de uso.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


class Database:
    def __init__(self, url: str) -> None:
        self._engine = create_engine(
            url,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,
            future=True,
        )
        self._session_factory = sessionmaker(
            bind=self._engine, autoflush=False, expire_on_commit=False,
        )

    @property
    def engine(self):
        return self._engine

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
