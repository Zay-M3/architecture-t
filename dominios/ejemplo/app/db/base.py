"""Base declarativa de SQLAlchemy.

Compartida por todos los dominios: es el metadata que Alembic usa para autogenerate, y
por eso `orquestador/alembic/env.py` importa los modelos de TODOS los dominios sobre
esta misma Base. Si cada dominio tuviera su propia Base, autogenerate vería las tablas
de los otros como sobrantes y propondría borrarlas.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
