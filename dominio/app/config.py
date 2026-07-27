"""Configuración del dominio.

Soporta Postgres y SQLite cambiando solo `DATABASE_URL`. Dos guardas al arrancar, y
las dos importan:

1. La invariante del pool (solo aplica a Postgres):

       GRPC_MAX_WORKERS  <=  DB_POOL_SIZE + DB_MAX_OVERFLOW

   Cada hilo del pool de gRPC que consulta la base ocupa una conexión. Si hay más hilos
   que conexiones, los de más esperan `DB_POOL_TIMEOUT` segundos y el proceso se congela
   sin razón aparente.

2. SQLite queda PROHIBIDO fuera de dev/test. La comodidad de "cambio el .env" es
   exactamente el mecanismo por el que un typo llega a producción, así que el arranque
   aborta en vez de servir tráfico sobre un archivo.

Detalle en 04-base-de-datos.md.
"""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DB_DEFAULT = "postgresql://dev:dev@localhost:5432/dev"
_DEV_ENVS = ("development", "test")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    DOMAIN_NAME: str = "ejemplo"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "info"

    # ── gRPC ────────────────────────────────────────────────────────────────
    GRPC_PORT: int = 50051
    GRPC_MAX_WORKERS: int = 10
    GRPC_MAX_MESSAGE_BYTES: int = 8 * 1024 * 1024
    GRPC_GRACE_SECONDS: int = 10

    # ── Base de datos ───────────────────────────────────────────────────────
    # postgresql://...        producción y dev con docker
    # sqlite:///./dominio.db  dev local sin docker
    # sqlite:///:memory:      tests
    DATABASE_URL: str = _INSECURE_DB_DEFAULT

    # Solo aplican a Postgres — SQLite ignora estos valores (ver db/session.py).
    DB_POOL_SIZE: int = 3       # PERMANENTES — en Postgres cada una es un proceso del SO
    DB_MAX_OVERFLOW: int = 7    # de pico: se cierran al devolverlas, son baratas
    DB_POOL_TIMEOUT: int = 10   # fallar rápido; 30 s congela el worker
    DB_POOL_RECYCLE: int = 1800  # el servidor corta conexiones ociosas

    # ── Observabilidad ──────────────────────────────────────────────────────
    # El tag `service` es lo que evita que los errores de todos los dominios se
    # mezclen en el mismo proyecto (ver 07, P9).
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    @property
    def IS_SQLITE(self) -> bool:  # noqa: N802 — se lee como el resto de la config
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def IS_DEV(self) -> bool:  # noqa: N802
        return self.APP_ENV in _DEV_ENVS

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        # SQLite nunca fuera de dev/test.
        if self.IS_SQLITE and not self.IS_DEV:
            raise RuntimeError(
                f"DATABASE_URL apunta a SQLite con APP_ENV={self.APP_ENV!r}. "
                "SQLite es solo para tests y desarrollo: no tiene JSONB, ni advisory "
                "locks, ni concurrencia de escritura real. Ver db/session.py."
            )

        if not self.IS_SQLITE:
            # La invariante del pool solo tiene sentido con un pool dimensionable.
            techo = self.DB_POOL_SIZE + self.DB_MAX_OVERFLOW
            if self.GRPC_MAX_WORKERS > techo:
                raise RuntimeError(
                    f"GRPC_MAX_WORKERS={self.GRPC_MAX_WORKERS} supera el techo de "
                    f"conexiones ({self.DB_POOL_SIZE} + {self.DB_MAX_OVERFLOW} = "
                    f"{techo}). Ver 04-base-de-datos.md."
                )

            if self.DATABASE_URL == _INSECURE_DB_DEFAULT and not self.IS_DEV:
                raise RuntimeError("DATABASE_URL es el default de desarrollo.")

        return self


settings = Settings()
