"""Interceptor de logging.

Registra método, duración y resultado de cada RPC, con el request-id para poder
correlacionar con el transformador.

Nota: un `ServerInterceptor` envuelve el *handler*, no la ejecución. Para medir el
tiempo hay que envolver la función del handler, no solo llamar a `continuation`.
"""

import logging
import time

import grpc

from app.interceptors.request_id import current_request_id

logger = logging.getLogger("rpc")


class LoggingInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if handler is None or not handler.unary_unary:
            # streaming: fuera del alcance de esta plantilla
            return handler

        method = handler_call_details.method

        def wrapper(request, context):
            started = time.perf_counter()
            try:
                response = handler.unary_unary(request, context)
            except Exception:
                logger.exception(
                    "rpc=%s request_id=%s ms=%.1f resultado=excepcion",
                    method, current_request_id(), (time.perf_counter() - started) * 1000,
                )
                raise
            logger.info(
                "rpc=%s request_id=%s ms=%.1f codigo=%s",
                method,
                current_request_id(),
                (time.perf_counter() - started) * 1000,
                context.code() or grpc.StatusCode.OK,
            )
            return response

        return grpc.unary_unary_rpc_method_handler(
            wrapper,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
