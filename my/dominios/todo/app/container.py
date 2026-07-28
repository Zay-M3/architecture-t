"""Composition Root.

Es el ÚNICO archivo del dominio donde se nombran clases concretas. Ningún use case,
controller ni repositorio importa otra concreción para instanciarla: reciben ABCs por
constructor y este archivo cablea las implementaciones.

Si un import de una clase concreta aparece fuera de acá, es un error de diseño: la
dependencia deja de ser sustituible y los tests no pueden hacer override.
"""

from dependency_injector import containers, providers

from app.config import settings
from app.controllers.todo import TodoController
from app.db.session import Database
from app.repositories.todo import TodoRepository
from app.services.clock import SystemClock
from app.use_cases.list_todos import ListTodosUseCase


class Container(containers.DeclarativeContainer):
    # ── Infraestructura ──────────────────────────────────────────────────────
    database = providers.Singleton(Database, url=settings.DATABASE_URL)
    clock = providers.Singleton(SystemClock)

    # ── Repositorios ─────────────────────────────────────────────────────────
    todo_repository = providers.Factory(TodoRepository, database=database)

    # ── Use cases: uno por acción ────────────────────────────────────────────
    list_todos_uc = providers.Factory(ListTodosUseCase, repo=todo_repository)

    # ── Controllers ──────────────────────────────────────────────────────────
    todo_controller = providers.Factory(TodoController, list_uc=list_todos_uc)
