"""Configuración del dominio.

La invariante del pool está documentada en 04-base-de-datos.md y se valida al arrancar:

    GRPC_MAX_WORKERS  <=  DB_POOL_SIZE + DB_MAX_OVERFLOW

Cada hilo del pool de gRPC que consulta la base ocupa una conexión. Si hay más hilos
que conexiones, los de más esperan `DB_POOL_TIMEOUT` segundos y el proceso se congela
sin razón aparente.
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

    # ── Base de datos (compartida entre todos los dominios) ─────────────────
    DATABASE_URL: str = _INSECURE_DB_DEFAULT
    DB_POOL_SIZE: int = 3       # PERMANENTES — en Postgres cada una es un proceso del SO
    DB_MAX_OVERFLOW: int = 7    # de pico: se cierran al devolverlas, son baratas
    DB_POOL_TIMEOUT: int = 10   # fallar rápido; 30 s congela el worker
    DB_POOL_RECYCLE: int = 1800  # el servidor corta conexiones ociosas

    # ── Observabilidad ──────────────────────────────────────────────────────
    # El tag `service` es lo que evita que los errores de todos los dominios
    # se mezclen en el mismo proyecto (ver 07, P9).
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        techo = self.DB_POOL_SIZE + self.DB_MAX_OVERFLOW
        if self.GRPC_MAX_WORKERS > techo:
            raise RuntimeError(
                f"GRPC_MAX_WORKERS={self.GRPC_MAX_WORKERS} supera el techo de "
                f"conexiones ({self.DB_POOL_SIZE} + {self.DB_MAX_OVERFLOW} = {techo}). "
                "Ver 04-base-de-datos.md."
            )
        if self.DATABASE_URL == _INSECURE_DB_DEFAULT and self.APP_ENV not in _DEV_ENVS:
            raise RuntimeError("DATABASE_URL es el default de desarrollo.")
        return self


settings = Settings()
