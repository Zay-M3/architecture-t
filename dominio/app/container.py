"""Composition Root.

Es el ÚNICO archivo del dominio donde se nombran clases concretas. Ningún use case,
controller ni repositorio importa otra concreción para instanciarla: reciben ABCs por
constructor y este archivo cablea las implementaciones.

Si un import de una clase concreta aparece fuera de acá, es un error de diseño: la
dependencia deja de ser sustituible y los tests no pueden hacer override.
"""

from dependency_injector import containers, providers

from app.config import settings
from app.db.session import Database
from app.services.clock import SystemClock


class Container(containers.DeclarativeContainer):
    # ── Infraestructura ──────────────────────────────────────────────────────
    database = providers.Singleton(Database, url=settings.DATABASE_URL)
    clock = providers.Singleton(SystemClock)

    # ── Repositorios ─────────────────────────────────────────────────────────
    # ejemplo_repository = providers.Factory(EjemploRepository, database=database)
    #
    # Lectura de tablas de OTRO dominio: un solo repositorio, y es el único lugar
    # que conoce el nombre de esas tablas (ver 04-base-de-datos.md).
    # catalog_reader = providers.Factory(CatalogReader, database=database)

    # ── Use cases: uno por acción ────────────────────────────────────────────
    # crear_ejemplo_uc = providers.Factory(
    #     CrearEjemploUseCase,
    #     repo=ejemplo_repository,
    #     clock=clock,
    # )

    # ── Controllers ──────────────────────────────────────────────────────────
    # ejemplo_controller = providers.Factory(
    #     EjemploController,
    #     crear_uc=crear_ejemplo_uc,
    # )
