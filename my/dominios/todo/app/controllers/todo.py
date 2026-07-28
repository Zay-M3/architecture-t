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

class TodoController:
    def __init__(self, list_uc=None) -> None:
        self._list_uc = list_uc
        
    
    def list(self, page, page_size, estados, nombre, context: grpc.ServicerContext):
            try:
                return self._list_uc.execute(
                    page=page, page_size=page_size, estados=estados, nombre=nombre
                )
            except ValidationError as e:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
            except Exception as e:
                self._internal(context, e)
                
    @staticmethod
    def _internal(context: grpc.ServicerContext, exc: Exception) -> None:
        """Nunca filtrar el detalle interno al cliente: el request-id ya está en el log
        del interceptor, y con eso se correlaciona."""
        import logging

        logging.getLogger(__name__).exception("error no manejado", exc_info=exc)
        context.abort(grpc.StatusCode.INTERNAL, "Error interno")
    