"""Controller de ejemplo.

Dos responsabilidades y ninguna más:
  1. Orquestar use cases.
  2. Traducir excepciones de dominio a grpc.StatusCode.

Es el ÚNICO lugar del dominio con manejo de errores. La tabla completa del mapeo está
en 03-contrato-grpc.md.

`context.abort()` corta la ejecución lanzando, así que no hace falta return después.
"""

import grpc

from app.exceptions.domain import (
    AlreadyExistsError,
    BusinessRuleViolation,
    InvalidTransitionError,
    NotFoundError,
    PermissionDeniedError,
    ReasonRequired,
    ValidationError,
)


class EjemploController:
    def __init__(self, get_uc=None, list_uc=None, confirmar_uc=None) -> None:
        self._get_uc = get_uc
        self._list_uc = list_uc
        self._confirmar_uc = confirmar_uc

    # ── Lectura ──────────────────────────────────────────────────────────────
    def get(self, ejemplo_id: str, context: grpc.ServicerContext):
        try:
            return self._get_uc.execute(ejemplo_id)
        except NotFoundError as e:
            context.abort(grpc.StatusCode.NOT_FOUND, str(e))
        except Exception as e:
            self._internal(context, e)

    def list(self, page, page_size, estados, search, context: grpc.ServicerContext):
        try:
            return self._list_uc.execute(
                page=page, page_size=page_size, estados=estados, search=search
            )
        except ValidationError as e:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            self._internal(context, e)

    # ── Mutación ─────────────────────────────────────────────────────────────
    def confirmar(
        self, ejemplo_id, motivo, actor_user_id, actor_user_name,
        context: grpc.ServicerContext,
    ):
        try:
            return self._confirmar_uc.execute(
                ejemplo_id=ejemplo_id,
                motivo=motivo,
                actor_user_id=actor_user_id,
                actor_user_name=actor_user_name,
            )
        except NotFoundError as e:
            context.abort(grpc.StatusCode.NOT_FOUND, str(e))
        except AlreadyExistsError as e:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, str(e))
        except (ReasonRequired, ValidationError) as e:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except (InvalidTransitionError, BusinessRuleViolation) as e:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
        except PermissionDeniedError as e:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, str(e))
        except Exception as e:
            self._internal(context, e)

    # ── Fallback ─────────────────────────────────────────────────────────────
    @staticmethod
    def _internal(context: grpc.ServicerContext, exc: Exception) -> None:
        """Nunca filtrar el detalle interno al cliente: el request-id ya está en el log
        del interceptor, y con eso se correlaciona."""
        import logging

        logging.getLogger(__name__).exception("error no manejado", exc_info=exc)
        context.abort(grpc.StatusCode.INTERNAL, "Error interno")
