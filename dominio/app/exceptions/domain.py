"""Excepciones de dominio.

El dominio las lanza; el CONTROLLER las traduce a grpc.StatusCode. Es el único lugar
del dominio con manejo de errores — los servicers no llevan try/except.

Mapeo (ver 03-contrato-grpc.md):

    NotFoundError            -> NOT_FOUND
    AlreadyExistsError       -> ALREADY_EXISTS
    ReasonRequired           -> INVALID_ARGUMENT
    ValidationError          -> INVALID_ARGUMENT
    InvalidTransitionError   -> FAILED_PRECONDITION
    BusinessRuleViolation    -> FAILED_PRECONDITION
    PermissionDeniedError    -> PERMISSION_DENIED
"""


class DomainError(Exception):
    """Raíz de todas las excepciones de dominio."""


class NotFoundError(DomainError):
    def __init__(self, entity: str, identifier: object) -> None:
        super().__init__(f"{entity} no encontrado: {identifier}")
        self.entity = entity
        self.identifier = identifier


class AlreadyExistsError(DomainError):
    def __init__(self, entity: str, field: str, value: object) -> None:
        super().__init__(f"{entity} ya existe con {field}={value}")
        self.entity = entity
        self.field = field
        self.value = value


class ValidationError(DomainError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


class BusinessRuleViolation(DomainError):
    """Nombre exacto heredado del CRM actual: NO es BusinessRuleError."""


class InvalidTransitionError(DomainError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"transición no permitida: {current} -> {target}")
        self.current = current
        self.target = target


class ReasonRequired(DomainError):
    def __init__(self, min_words: int, got: int) -> None:
        super().__init__(
            f"se requiere un motivo de al menos {min_words} palabras (recibidas: {got})"
        )
        self.min_words = min_words
        self.got = got


class PermissionDeniedError(DomainError):
    """Reservado: auth va en un servicio aparte, fuera de este diseño."""
