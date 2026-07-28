"""Acceso a datos de tareas.

Lo único que sabe SQL. El use case de arriba no ve SQLAlchemy, y por eso se puede
testear con un doble sin base de datos.
"""

from sqlalchemy import func, select

from app.db.session import Database
from app.domain.todo import Todo


class TodoRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    def list(
        self,
        page: int,
        page_size: int,
        nombre: str = "",
    ) -> tuple[list[Todo], int]:
        """Página de tareas + total de coincidencias.

        Dos consultas: una de datos y otra de count. El total se cuenta en SQL, no
        trayendo todas las filas para hacer len() en Python.
        """
        filtros = []
        if nombre:
            filtros.append(Todo.nombre.ilike(f"%{nombre}%"))

        with self._db.session() as s:
            total = s.scalar(
                select(func.count()).select_from(Todo).where(*filtros)
            ) or 0

            filas = s.scalars(
                select(Todo)
                .where(*filtros)
                .order_by(Todo.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            ).all()

        return list(filas), total
