"""Listar tareas.

Un use case por acción. Recibe el repositorio por constructor: no importa ninguna
clase concreta, eso lo decide el container.
"""

from app.exceptions.domain import ValidationError
from app.repositories.todo import TodoRepository

MAX_PAGE_SIZE = 100


class ListTodosUseCase:
    def __init__(self, repo: TodoRepository) -> None:
        self._repo = repo

    def execute(
        self,
        page: int = 1,
        page_size: int = 50,
        estados: list[int] | None = None,
        nombre: str = "",
    ):
        # El tope existe para que nadie pida page_size=1000000 y tumbe el proceso.
        if page < 1:
            raise ValidationError("page debe ser >= 1")
        if page_size < 1 or page_size > MAX_PAGE_SIZE:
            raise ValidationError(f"page_size debe estar entre 1 y {MAX_PAGE_SIZE}")

        return self._repo.list(page=page, page_size=page_size, nombre=nombre)
