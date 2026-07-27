# 03 — El contrato gRPC

> El `.proto` es el contrato **y** la documentación. Es más fuerte que un OpenAPI:
> un OpenAPI puede desviarse de lo que el código hace y nadie se entera; un `.proto`
> no puede, porque si no coincide el codegen no compila.

## Organización

```
proto/
└── <dominio>/v1/
    └── <dominio>.proto
```

Versionado en la ruta (`v1`). Un cambio incompatible es `v2`, no una edición de `v1`.

**Compatible** (no rompe clientes): agregar un campo con número nuevo, agregar un
método, agregar un valor a un enum.
**Incompatible** (exige `v2`): cambiar el tipo o el número de un campo, quitar un
campo, renombrar un método.

## Convenciones

### Dinero: siempre `string`, nunca `double`

```protobuf
message PurchaseOrderLine {
  int32 quantity = 1;
  string unit_cost = 2;      // "1234.56" — se parsea con Decimal
  string line_subtotal = 3;
}
```

`double` es `float64` y pierde precisión en importes. **Prohibido.** `Decimal` no
existe en proto3, así que va como `string` y se parsea con `Decimal(valor)` del lado
del servidor. Es el patrón estándar en APIs financieras.

### Fechas: `google.protobuf.Timestamp` para instantes, `string` ISO para fechas

```protobuf
import "google/protobuf/timestamp.proto";

message PurchaseOrder {
  string issue_date = 5;                          // "2026-07-27" — fecha sin hora
  google.protobuf.Timestamp created_at = 6;       // instante con zona
}
```

Una fecha de emisión no tiene hora ni zona; forzarla a `Timestamp` inventa un
mediodía que después alguien interpreta mal.

### Enums: prefijo y cero reservado

```protobuf
enum PurchaseOrderStatus {
  PURCHASE_ORDER_STATUS_UNSPECIFIED = 0;   // el 0 SIEMPRE es "sin especificar"
  PURCHASE_ORDER_STATUS_BORRADOR = 1;
  PURCHASE_ORDER_STATUS_CONFIRMADO = 2;
  PURCHASE_ORDER_STATUS_PENDIENTE_RECEPCION = 3;
  PURCHASE_ORDER_STATUS_CON_RECEPCION = 4;
  PURCHASE_ORDER_STATUS_PENDIENTE_FACTURA = 5;
  PURCHASE_ORDER_STATUS_CON_FACTURA = 6;
  PURCHASE_ORDER_STATUS_CERRADO = 7;
  PURCHASE_ORDER_STATUS_CANCELADO = 8;
}
```

El `0` reservado importa porque proto3 no distingue "no enviado" de "valor por
defecto". Sin `UNSPECIFIED`, un campo ausente parecería `BORRADOR`.

### Actor: explícito en cada mutación

```protobuf
message ApprovePurchaseOrderRequest {
  string id = 1;
  string reason = 2;
  int32 actor_user_id = 3;
  string actor_user_name = 4;
}
```

Toda mutación lleva quién la hizo, porque el dominio tiene que registrarlo. El actor
lo pone el transformador desde la sesión; el dominio no lo adivina.

### Paginación: siempre en la respuesta

```protobuf
message ListPurchaseOrdersRequest {
  int32 page = 1;
  int32 page_size = 2;
  repeated PurchaseOrderStatus statuses = 3;
  string search = 4;
}
message ListPurchaseOrdersResponse {
  repeated PurchaseOrder items = 1;
  int32 total = 2;         // 1 query de datos + 1 count, ambas en SQL
}
```

## Errores: excepción de dominio → `StatusCode`

El mapeo vive en el controller y es el mismo en todos los dominios:

| Excepción de dominio | `grpc.StatusCode` | Cuándo |
|---|---|---|
| `NotFoundError` | `NOT_FOUND` | el recurso no existe |
| `AlreadyExistsError` | `ALREADY_EXISTS` | duplicado (CIF de proveedor, short_code) |
| `ReasonRequired` | `INVALID_ARGUMENT` | falta el motivo o tiene <10 palabras |
| validación de datos | `INVALID_ARGUMENT` | cantidad ≤0, importe no parseable, sin líneas |
| `InvalidTransitionError` | `FAILED_PRECONDITION` | transición de estado no permitida |
| `BusinessRuleViolation` | `FAILED_PRECONDITION` | regla de negocio violada |
| `PermissionDeniedError` | `PERMISSION_DENIED` | sin permiso (cuando llegue auth) |
| falla de infraestructura | `INTERNAL` | y se loguea con el request-id |

Del lado del transformador el mapeo inverso a HTTP:

| `StatusCode` | HTTP |
|---|---|
| `NOT_FOUND` | 404 |
| `ALREADY_EXISTS` | 409 |
| `INVALID_ARGUMENT` | 422 |
| `FAILED_PRECONDITION` | 409 |
| `PERMISSION_DENIED` | 403 |
| `UNAUTHENTICATED` | 401 |
| `UNAVAILABLE` / `DEADLINE_EXCEEDED` | 503 |
| `INTERNAL` | 500 |

## Webhooks de terceros: el túnel

Twilio, Meta, Shopify y Sendcloud hacen POST HTTP. No pueden hablar gRPC. Y ningún
dominio expone HTTP. La salida: **el transformador no transforma el webhook, lo
tunela.**

```protobuf
// proto/shared/v1/webhook.proto
message InboundWebhook {
  string provider = 1;                    // "twilio" | "meta" | "shopify" | "sendcloud"
  string path = 2;                        // el path original
  map<string, string> headers = 3;        // incluye la cabecera de firma
  bytes raw_body = 4;                     // CRUDO, sin parsear
}
message InboundWebhookResponse {
  int32 http_status = 1;                  // el transformador lo hace eco
  bytes body = 2;
}

service WebhookService {
  rpc HandleInbound(InboundWebhook) returns (InboundWebhookResponse);
}
```

**Tres detalles que si se pasan por alto rompen:**

1. **`raw_body` va crudo.** Meta firma sobre los bytes exactos con
   `X-Hub-Signature-256`. Si el transformador deserializa y reserializa, la firma no
   valida nunca. El dominio valida con su propio secreto — así los secretos de
   proveedor se quedan en Python y no se mudan al transformador.
2. **El status lo decide el dominio**, no el transformador. Twilio y Meta reintentan
   ante cualquier cosa que no sea 2xx.
3. **ACK rápido, procesar después.** Meta espera 200 en pocos segundos. El dominio
   acepta los bytes, responde 200 y procesa por su cuenta. Si el procesamiento cuelga
   del webhook, se disparan reintentos.

## Documentación: reflection

No hay Swagger porque no hay HTTP. El equivalente lo dice la propia documentación de
gRPC:

> *"Reflection is a protocol that gRPC servers can use to declare the protobuf-defined
> APIs they export... **It can be compared to serving an OpenAPI document for a REST
> API.**"*

| Necesidad | Herramienta |
|---|---|
| Explorar y probar a mano, como Swagger UI | **Reflection** (`grpcio-reflection`) + Postman, Insomnia, grpcurl o Apidog |
| Documento navegable en HTML/Markdown | **`protoc-gen-doc`**, desde los comentarios del `.proto` |
| El contrato | **El `.proto`** |

Reflection queda **encendida**: todo está detrás del transformador, nada expuesto a
internet. En un servicio público se apagaría porque revela la superficie completa.

## Generar los stubs

```bash
python -m grpc_tools.protoc \
  --proto_path=proto \
  --python_out=app/grpc_gen \
  --grpc_python_out=app/grpc_gen \
  --pyi_out=app/grpc_gen \
  proto/purchasing/v1/purchasing.proto
```

`--pyi_out` genera los stubs de tipos, que hacen falta para que el type checker vea
los mensajes.

`app/grpc_gen/` **no se commitea** — se genera en el build y con un comando del CLI.

> **Gotcha conocido:** `grpc_tools.protoc` emite `import xxx_pb2` con rutas absolutas
> que se rompen dentro de un paquete. Hay que parchear los imports generados a
> relativos, o generar desde la raíz del paquete. El CLI lo hace en el mismo comando.

## Checklist de un `.proto` nuevo

- [ ] Versionado en la ruta (`<dominio>/v1/`)
- [ ] Dinero como `string`, cero `double`
- [ ] Enums con `_UNSPECIFIED = 0`
- [ ] Cada mutación lleva `actor_user_id` y `actor_user_name`
- [ ] Cada listado devuelve `items` + `total`
- [ ] Comentarios en los mensajes y métodos — son la documentación que sale en `protoc-gen-doc`
- [ ] Números de campo nunca reutilizados (si se quita uno, se marca `reserved`)
