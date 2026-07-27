"""Alembic: cadena ÚNICA para toda la plataforma.

Vive en el orquestador, no en los dominios, porque con base compartida y FKs entre
dominios hace falta orden determinista.

⚠  EL PIE DE PLOMO MÁS IMPORTANTE DE TODO EL REPO
   `target_metadata` tiene que incluir los modelos de TODOS los dominios. Si falta uno,
   `autogenerate` va a ver sus tablas como sobrantes y va a emitir `op.drop_table()`
   para cada una. Por eso los imports de abajo llevan `noqa: F401`: parecen no usarse,
   pero registran los modelos en el metadata compartido.

   Y siempre leer el diff generado antes de aplicarlo.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Los dominios están fuera del paquete del orquestador: hay que ponerlos en el path.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.db.base import Base  # noqa: E402

# ── Modelos de TODOS los dominios ────────────────────────────────────────────
# Agregar una línea por dominio nuevo. Omitir una = migración que borra sus tablas.
from dominios.ejemplo.app.db import models as _ejemplo_models  # noqa: E402,F401
# from dominios.compras.app.db import models as _compras_models  # noqa: E402,F401

target_metadata = Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,   # las migraciones no necesitan pool
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
