"""Modelo de tarea.

Una sola tabla. `estado` se guarda como el entero del enum del .proto para no tener
que mapear nombres en los dos sentidos: lo que hay en la base es exactamente lo que
viaja por el cable.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Espejo de EjemploEstado en todo.proto.
ESTADO_UNSPECIFIED = 0
ESTADO_BORRADOR = 1
ESTADO_CONFIRMADO = 2


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(32), default="")
    nombre: Mapped[str] = mapped_column(String(200))
    estado: Mapped[int] = mapped_column(Integer, default=ESTADO_BORRADOR)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int] = mapped_column(Integer, default=0)
    created_by_user_name: Mapped[str] = mapped_column(String(100), default="")
