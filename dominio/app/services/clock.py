"""Reloj inyectable.

Existe para que los tests sean deterministas: un use case que llama a
`datetime.now()` directo no se puede testear sin congelar el tiempo del proceso.
Se inyecta por constructor como cualquier otra dependencia.
"""

from abc import ABC, abstractmethod
from datetime import date, datetime, timezone


class IClock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        """Instante actual, siempre con zona (UTC)."""

    @abstractmethod
    def today(self) -> date:
        """Fecha actual."""


class SystemClock(IClock):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def today(self) -> date:
        return datetime.now(timezone.utc).date()


class FrozenClock(IClock):
    """Para tests: el tiempo no avanza salvo que se lo mueva a mano."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant

    def today(self) -> date:
        return self._instant.date()

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._instant += timedelta(seconds=seconds)
