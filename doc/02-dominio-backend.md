# 02 — Cómo se construye un dominio

> Un dominio es un proceso Python que expone **solo gRPC**. Sin FastAPI, sin uvicorn,
> sin HTTP. Arquitectura limpia por capas, inyección de dependencias pura, servidor
> sincrónico.

## Estructura de carpetas

```
dominio-compras/
├── pyproject.toml              # gestionado con uv
├── proto/
│   └── purchasing/v1/
│       └── purchasing.proto
├── alembic/                    # ver 04 — la cadena es global, vive en el orquestador
├── app/
│   ├── server.py               # bootstrap: monta servicers, interceptores, reflection
│   ├── config.py               # pydantic-settings
│   ├── container.py            # Composition Root — el ÚNICO lugar con concreciones
│   │
│   ├── servicers/              # ENTRADA gRPC (equivale a los routers de FastAPI)
│   │   ├── __init__.py
│   │   ├── purchase_orders.py
│   │   ├── suppliers.py
│   │   ├── receptions.py
│   │   └── webhooks.py         # recibe los webhooks tunelados por el transformador
│   │
│   ├── interceptors/           # transversal: logging, request-id, (auth cuando llegue)
│   │   ├── request_id.py
│   │   └── logging.py
│   │
│   ├── controllers/            # orquesta use cases + mapea errores de dominio a StatusCode
│   ├── use_cases/              # lógica de negocio — una carpeta por acción
│   │   └── <accion>/
│   │       ├── dto.py
│   │       └── use_case.py
│   ├── repositories/           # ORM ↔ entidades de dominio
│   ├── domain/                 # entidades + ABC — SOLO stdlib
│   │   ├── entities.py
│   │   └── ports.py
│   ├── services/               # adaptadores: PDF, XLSX, Excel, OCR, cache
│   ├── db/
│   │   ├── base.py
│   │   ├── session.py
│   │   └── models/             # ORM SQLAlchemy
│   ├── constants/              # enums, estados, literales de negocio
│   ├── exceptions/             # excepciones de dominio
│   ├── utils/                  # helpers sin estado (money, clock, sanitize)
│   └── grpc_gen/               # stubs generados — NO se commitea
└── tests/
    ├── unit/
    └── integration/
```

## Las capas y quién puede importar a quién

```
servicers → controllers → use_cases → repositories → domain
                              ↓
                          services
```

| Capa | Responsabilidad | Puede importar |
|------|----------------|----------------|
| `servicers/` | Deserializa el mensaje proto, llama al controller, serializa la respuesta. **Sin lógica, sin try/except.** | `controllers`, `grpc_gen` |
| `controllers/` | Orquesta use cases. **Único lugar con manejo de errores**: traduce excepciones de dominio a `StatusCode`. | `use_cases`, `exceptions` |
| `use_cases/` | Lógica de negocio. Una carpeta por acción, con `dto.py` y `use_case.py`. Recibe ABCs, nunca concreciones. | `domain`, `constants` |
| `repositories/` | Traduce ORM ↔ entidades de dominio. Implementa las ABC de `domain/ports.py`. | `db/models`, `domain` |
| `domain/` | Dataclasses + ABC. **Solo stdlib.** No conoce gRPC, ni SQLAlchemy, ni nada externo. | stdlib |
| `services/` | Adaptadores a lo de afuera: generar PDF, leer Excel, llamar al OCR, cache. Detrás de ABC si hay más de una implementación. | `domain/ports` |
| `utils/` | Funciones puras sin estado. | stdlib |

**La regla que no se negocia:** las concreciones se nombran **solo** en `container.py`.
Ningún use case, controller ni repositorio importa otra clase concreta para
instanciarla.

## El servidor

`grpcio` sincrónico con thread pool. Reflection encendida (es interno, no hay razón
para apagarla) y health checking para que Docker sepa si el proceso está sano.

```python
# app/server.py
from concurrent import futures
import grpc
from grpc_reflection.v1alpha import reflection
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.config import settings
from app.container import Container
from app.grpc_gen.purchasing.v1 import purchasing_pb2, purchasing_pb2_grpc
from app.interceptors.request_id import RequestIdInterceptor
from app.interceptors.logging import LoggingInterceptor
from app.servicers.purchase_orders import PurchaseOrderServicer


def serve() -> None:
    container = Container()

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=settings.GRPC_MAX_WORKERS),
        interceptors=[RequestIdInterceptor(), LoggingInterceptor()],
        options=[
            ("grpc.max_receive_message_length", settings.GRPC_MAX_MESSAGE_BYTES),
            ("grpc.max_send_message_length", settings.GRPC_MAX_MESSAGE_BYTES),
        ],
    )

    purchasing_pb2_grpc.add_PurchasingServiceServicer_to_server(
        PurchaseOrderServicer(controller=container.purchase_order_controller()),
        server,
    )

    # Health checking: lo consume grpc_health_probe desde el HEALTHCHECK de Docker
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Reflection: es el equivalente a servir un OpenAPI. Lo usan grpcurl, Postman, Apidog.
    reflection.enable_server_reflection(
        (
            purchasing_pb2.DESCRIPTOR.services_by_name["PurchasingService"].full_name,
            health_pb2.DESCRIPTOR.services_by_name["Health"].full_name,
            reflection.SERVICE_NAME,
        ),
        server,
    )

    server.add_insecure_port(f"[::]:{settings.GRPC_PORT}")
    server.start()
    server.wait_for_termination()
```

### Concurrencia y el techo del pool

`max_workers` es cuántos RPCs se atienden en paralelo. Cada hilo que consulta la base
ocupa una conexión, así que hay una invariante que **no se puede violar**:

```
max_workers  <=  DB_POOL_SIZE + DB_MAX_OVERFLOW
```

Números de arranque (justificación en [`04-base-de-datos.md`](04-base-de-datos.md)):

```
GRPC_MAX_WORKERS = 10
DB_POOL_SIZE     = 3
DB_MAX_OVERFLOW  = 7      →  10 ≤ 3 + 7  ✓
```

> **Un solo proceso por dominio.** Multiproceso con `SO_REUSEPORT` no sirve acá: reparte
> **conexiones**, no requests, y el transformador abre **una** conexión HTTP/2 por
> dominio y multiplexa todo por ahí. Los procesos extra quedarían sin tráfico. Si algún
> día hace falta, la salida es un puerto por proceso y balanceo del lado del cliente.

## Servicer: cómo se ve

Delgado por diseño. Deserializar, llamar, serializar.

```python
# app/servicers/purchase_orders.py
from app.grpc_gen.purchasing.v1 import purchasing_pb2, purchasing_pb2_grpc


class PurchaseOrderServicer(purchasing_pb2_grpc.PurchasingServiceServicer):
    def __init__(self, controller):
        self._controller = controller

    def GetPurchaseOrder(self, request, context):
        result = self._controller.get(request.short_code, context)
        return purchasing_pb2.PurchaseOrder(**result)

    def ApprovePurchaseOrder(self, request, context):
        result = self._controller.approve(
            po_id=request.id,
            reason=request.reason,
            actor_user_id=request.actor_user_id,
            actor_user_name=request.actor_user_name,
            context=context,
        )
        return purchasing_pb2.PurchaseOrder(**result)
```

## Controller: el único lugar con manejo de errores

```python
# app/controllers/purchase_order_controller.py
import grpc
from app.exceptions.domain import (
    NotFoundError, BusinessRuleViolation, InvalidTransitionError, ReasonRequired,
)


class PurchaseOrderController:
    def __init__(self, get_uc, approve_uc):
        self._get_uc = get_uc
        self._approve_uc = approve_uc

    def approve(self, po_id, reason, actor_user_id, actor_user_name, context):
        try:
            return self._approve_uc.execute(ApproveInput(...)).as_dict()
        except NotFoundError as e:
            context.abort(grpc.StatusCode.NOT_FOUND, str(e))
        except ReasonRequired as e:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except InvalidTransitionError as e:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
        except BusinessRuleViolation as e:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
```

El mapeo completo de excepciones a `StatusCode` está en
[`03-contrato-grpc.md`](03-contrato-grpc.md).

## Inyección de dependencias

`dependency-injector`, igual que en el CRM actual pero **sin la capa de FastAPI**.
Sin `Depends()` — el container se resuelve directo, que es más simple.

```python
# app/container.py
from dependency_injector import containers, providers

from app.config import settings
from app.db.session import Database
from app.repositories.purchase_order_repository import PurchaseOrderRepository
from app.use_cases.approve_purchase_order.use_case import ApprovePurchaseOrderUseCase
from app.controllers.purchase_order_controller import PurchaseOrderController
from app.services.clock import SystemClock


class Container(containers.DeclarativeContainer):
    database = providers.Singleton(Database, url=settings.DATABASE_URL)
    clock = providers.Singleton(SystemClock)

    purchase_order_repository = providers.Factory(
        PurchaseOrderRepository, database=database,
    )

    approve_purchase_order_uc = providers.Factory(
        ApprovePurchaseOrderUseCase,
        po_repo=purchase_order_repository,
        clock=clock,
    )

    purchase_order_controller = providers.Factory(
        PurchaseOrderController,
        approve_uc=approve_purchase_order_uc,
    )
```

## Interceptores

Son el equivalente al middleware de FastAPI: corren antes de cada RPC.

```python
# app/interceptors/request_id.py
import uuid
import grpc

_HEADER = "x-request-id"


class RequestIdInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        md = dict(handler_call_details.invocation_metadata)
        request_id = md.get(_HEADER) or str(uuid.uuid4())
        # dejarlo en un contextvar para que el logger lo tome
        set_request_id(request_id)
        return continuation(handler_call_details)
```

**Dos detalles verificados que no son obvios:**

- `handler_call_details` tiene **exactamente dos** atributos: `method` y
  `invocation_metadata`. No hay `authority`, ni `host`, ni `peer`.
- **`context.peer()` (la IP del cliente) NO está disponible en un interceptor** — los
  interceptores corren antes de que se elija el handler. Si hace falta auditar la IP,
  va dentro del servicer.

Cuando llegue auth, el patrón es abortar desde el interceptor devolviendo un handler
en vez de llamar a `continuation`:

```python
return grpc.unary_unary_rpc_method_handler(
    lambda req, ctx: ctx.abort(grpc.StatusCode.UNAUTHENTICATED, "Token inválido")
)
```

## Dependencias

Sin FastAPI, sin uvicorn, sin gunicorn.

```toml
# pyproject.toml — gestionado con uv
[project]
requires-python = ">=3.12"
dependencies = [
    "grpcio>=1.66",
    "grpcio-tools>=1.66",
    "grpcio-reflection>=1.66",
    "grpcio-health-checking>=1.66",
    "protobuf>=5.28",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg2-binary>=2.9",
    "dependency-injector>=4.41",
    "pydantic>=2.9",
    "pydantic-settings>=2.5",
]

[dependency-groups]
dev = ["pytest", "pytest-cov", "ruff", "watchfiles"]
```

**Sobre Pydantic:** el proto ya valida estructura y tipos, así que Pydantic queda solo
para `pydantic-settings` (config) y para reglas de negocio que el proto no puede
expresar — motivo con ≥10 palabras, decimales normalizados. No se usa para validar el
borde: eso ya lo hizo protobuf.

## Desarrollo: no hay `--reload`

gRPC no trae recarga automática. Se envuelve el proceso con `watchfiles`, que es lo
que uvicorn usa por dentro. El CLI lo expone como un comando
([`06-orquestador-typer.md`](06-orquestador-typer.md)):

```bash
watchfiles "python -m app.server" app/
```

## Checklist de un dominio terminado

- [ ] `domain/` no importa nada fuera de stdlib
- [ ] Ningún servicer tiene `try/except`
- [ ] Todas las concreciones están solo en `container.py`
- [ ] Cada use case tiene su `dto.py` y su carpeta propia
- [ ] `max_workers ≤ DB_POOL_SIZE + DB_MAX_OVERFLOW`
- [ ] Reflection y health checking encendidos
- [ ] Cero magic strings: estados, rutas de proto y literales en `constants/`
- [ ] `ruff` y el type checker en verde
- [ ] Tests unitarios de use cases + integración de servicers
