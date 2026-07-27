"""Interceptor de request-id.

Los interceptores son el equivalente al middleware de FastAPI: corren antes de cada RPC.

Dos detalles verificados en el fuente de grpcio que no son obvios:

1. `handler_call_details` tiene EXACTAMENTE dos atributos: `method` y
   `invocation_metadata`. No hay `authority`, ni `host`, ni `peer`.
2. `context.peer()` (la IP del cliente) NO está disponible acá — los interceptores
   corren antes de que se elija el handler. Si hace falta auditar la IP, va dentro del
   servicer.
"""

import uuid
from contextvars import ContextVar

import grpc

REQUEST_ID_HEADER = "x-request-id"

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def current_request_id() -> str:
    return _request_id.get()


class RequestIdInterceptor(grpc.ServerInterceptor):
    """Propaga el request-id que manda el transformador, o genera uno."""

    def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata or ())
        _request_id.set(metadata.get(REQUEST_ID_HEADER) or str(uuid.uuid4()))
        return continuation(handler_call_details)
