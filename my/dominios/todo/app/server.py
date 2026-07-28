"""Bootstrap del servidor gRPC.

Servidor SINCRÓNICO con thread pool (decisión D2). Sin FastAPI, sin uvicorn.

Se levanta con:  python -m app.server
En desarrollo:   watchfiles "python -m app.server" app/
"""

import logging
import signal
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

from app.config import settings
from app.container import Container
from app.interceptors.logging import LoggingInterceptor
from app.interceptors.request_id import RequestIdInterceptor

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)


def _build_server(container: Container) -> tuple[grpc.Server, health.HealthServicer]:
    server = grpc.server(
        futures.ThreadPoolExecutor(
            max_workers=settings.GRPC_MAX_WORKERS,
            thread_name_prefix=f"{settings.DOMAIN_NAME}-rpc",
        ),
        interceptors=[RequestIdInterceptor(), LoggingInterceptor()],
        options=[
            ("grpc.max_receive_message_length", settings.GRPC_MAX_MESSAGE_BYTES),
            ("grpc.max_send_message_length", settings.GRPC_MAX_MESSAGE_BYTES),
        ],
    )

    service_names: list[str] = []

    # ── Servicers del dominio ────────────────────────────────────────────────
    # El import va acá dentro y no arriba: los stubs se generan (oc proto gen) y no
    # se versionan, así que importarlos a nivel de módulo rompe cualquier import de
    # app.server —tests incluidos— cuando todavía no se han generado.
    from app.grpc_gen.todo.v1 import todo_pb2, todo_pb2_grpc
    from app.servicers.todo import TodoService

    todo_pb2_grpc.add_TodoServiceServicer_to_server(
        TodoService(controller=container.todo_controller()), server,
    )
    # Registrarlo en service_names es lo que lo hace visible a reflection; si se
    # olvida, el servicio responde pero grpcurl y Postman no lo descubren.
    service_names.append(
        todo_pb2.DESCRIPTOR.services_by_name["TodoService"].full_name
    )

    # ── Health checking ──────────────────────────────────────────────────────
    # Lo consume grpc_health_probe desde el HEALTHCHECK del contenedor.
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    service_names.append(health_pb2.DESCRIPTOR.services_by_name["Health"].full_name)

    # ── Reflection ───────────────────────────────────────────────────────────
    # Es el equivalente a servir un OpenAPI: con esto grpcurl, Postman, Insomnia y
    # Apidog descubren los métodos y la forma de los mensajes en runtime.
    # Queda encendida porque todo está detrás del transformador, nada expuesto.
    service_names.append(reflection.SERVICE_NAME)
    reflection.enable_server_reflection(tuple(service_names), server)

    return server, health_servicer


def _create_tables(container: Container) -> None:
    """Crea el esquema en SQLite.

    Solo en SQLite y solo porque todavía no hay Alembic: con Postgres el esquema lo
    dueña la migración, y un create_all silencioso taparía que falta migrar.
    """
    if not container.database().is_sqlite:
        return

    from app.db.base import Base
    from app.domain import todo as _todo  # noqa: F401 — registra la tabla en Base

    Base.metadata.create_all(container.database().engine)
    logger.info("esquema SQLite asegurado")


def serve() -> None:
    container = Container()
    _create_tables(container)
    server, health_servicer = _build_server(container)

    server.add_insecure_port(f"[::]:{settings.GRPC_PORT}")
    server.start()

    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    logger.info(
        "dominio=%s escuchando gRPC en :%s (max_workers=%s, pool=%s+%s)",
        settings.DOMAIN_NAME,
        settings.GRPC_PORT,
        settings.GRPC_MAX_WORKERS,
        settings.DB_POOL_SIZE,
        settings.DB_MAX_OVERFLOW,
    )

    def _shutdown(signum, _frame):
        """Apagado ordenado: dejar de aceptar, terminar lo en vuelo, salir."""
        logger.info("señal %s recibida — apagando", signum)
        health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
        server.stop(settings.GRPC_GRACE_SECONDS)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    server.wait_for_termination()
    logger.info("apagado limpio")


if __name__ == "__main__":
    serve()
