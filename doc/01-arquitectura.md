# 01 — Arquitectura

## El mapa

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLI Typer (orquestador)                                            │
│  docker up/down · alembic upgrade · pytest · ruff · type            │
└─────────────────────────────────────────────────────────────────────┘
          │ levanta                              │ migra
          ▼                                      ▼
┌──────────────────────┐                 ┌──────────────────┐
│ dominio: compras     │                 │                  │
│  servidor gRPC :50051│────────────────▶│                  │
├──────────────────────┤                 │  PostgreSQL      │
│ dominio: <otro>      │                 │  (una instancia) │
│  servidor gRPC :50052│────────────────▶│                  │
├──────────────────────┤                 │                  │
│ dominio: <otro>      │────────────────▶│                  │
│  servidor gRPC :50053│                 └──────────────────┘
└──────────────────────┘
          ▲
          │ gRPC (única forma de entrada)
          │
┌─────────────────────────────────────────────────────────────────────┐
│  Transformador — Astro SSR                                          │
│  · llama a los dominios por gRPC desde el frontmatter               │
│  · renderiza HTML en el servidor                                    │
│  · Actions para mutaciones                                          │
│  · endpoint SSE para push                                           │
│  · tunela webhooks de terceros hacia el dominio dueño               │
└─────────────────────────────────────────────────────────────────────┘
          │ HTML + SSE
          ▼
     navegador
```

## Las cuatro piezas

### Dominio

Un proceso Python que expone **solo gRPC**. Contiene toda la lógica de su área de
negocio, organizada por capas (arquitectura limpia). No sabe qué lo llama, no sabe
qué renderiza sus datos, y no habla con otros dominios.

Un dominio = una carpeta = un proceso = un puerto.

Detalle en [`02-dominio-backend.md`](02-dominio-backend.md).

### Transformador

El servidor de Astro. Es la **única** puerta de entrada desde internet. Hace tres
cosas:

1. Recibe requests HTTP del navegador, llama a los dominios por gRPC, renderiza HTML.
2. Sostiene el canal SSE para empujar actualizaciones al navegador.
3. **Tunela** los webhooks de terceros: recibe el POST, lo reenvía crudo por gRPC al
   dominio dueño, y devuelve el status que ese dominio decida.

No tiene lógica de negocio. Traduce protocolos y renderiza.

Detalle en [`05-transformador-y-frontend.md`](05-transformador-y-frontend.md).

### Base de datos

**Una sola instancia de PostgreSQL**, compartida por todos los dominios. Cada
dominio accede por su propio pool, con su propia capa de repositorios, y respeta
las reglas de propiedad de tablas.

Detalle en [`04-base-de-datos.md`](04-base-de-datos.md).

### Orquestador

Un CLI construido con Typer. Es la interfaz humana de la plataforma: levanta los
contenedores, corre las migraciones, ejecuta los tests, pasa ruff y el type checker.

**No es un gestor de procesos.** Docker levanta y supervisa; Typer solo da los
comandos.

Detalle en [`06-orquestador-typer.md`](06-orquestador-typer.md).

## Las reglas que definen la arquitectura

### 1. Los dominios hablan gRPC y nada más

Sin FastAPI, sin uvicorn, sin HTTP. Un servidor `grpcio` puro.

**Por qué:** el único consumidor es el transformador, y el transformador habla gRPC.
Un servidor HTTP sin consumidores es superficie que hay que mantener, documentar y
asegurar sin que nadie la use. Los tres candidatos habituales a necesitar HTTP están
resueltos de otra forma:

| Candidato | Cómo se resuelve sin HTTP |
|---|---|
| Webhooks de terceros | El transformador los tunela por gRPC |
| Health checks | `grpc.health.v1.Health` + `grpc_health_probe` |
| Documentación | Server reflection + `protoc-gen-doc` |

### 2. Los dominios no se hablan entre sí

Cero llamadas dominio → dominio. Si un dominio necesita datos de otro, los lee de la
base de datos compartida a través de su propia capa de repositorios, respetando las
reglas de propiedad ([`04-base-de-datos.md`](04-base-de-datos.md)).

**Por qué:** una malla de llamadas entre N dominios es N² contratos y un grafo de
dependencias que hay que ordenar en cada arranque. Con una base compartida el dato
ya está disponible sin red en medio, y sin perder la transaccionalidad.

### 3. El servidor gRPC es sincrónico

`grpc.server(ThreadPoolExecutor(max_workers=10))`. Los servicers son `def`. La capa
de repositorios usa SQLAlchemy sincrónico.

**Por qué:** no hay ninguna operación del dominio que gane con async — son consultas
secuenciales a la base, más generación de PDF, XLSX e importación de Excel, que son
bloqueantes por naturaleza. Y la asimetría del error decide: si en sync te olvidás de
optimizar algo, un hilo queda ocupado más tiempo; si en async te olvidás de un
`run_in_executor`, se congela el proceso entero (la documentación de gRPC lo dice
así: *"can potentially starve all RPCs"*).

El escape existe igual: `asyncio.run()` dentro de un handler para el caso puntual que
necesite paralelismo.

### 4. El frontend no tiene framework de cliente

Los componentes `.astro` renderizan a HTML estático sin runtime en el navegador. La
interactividad sale de tres mecanismos: **Astro Actions** (mutaciones), **`<script>`
+ Web Components** (interacción local) y **SSE** (actualizaciones empujadas).

**Por qué:** el cálculo del total, las validaciones y las reglas de estado existen en
el dominio de todas formas. Con estado en el cliente se escriben dos veces y divergen.
Renderizando en el servidor se escriben una sola vez, donde corresponde.

### 5. Una sola base de datos, migraciones globales

Alembic con una cadena única, ejecutada desde el CLI. Esto habilita transacciones que
cruzan dominios y FKs entre ellos, y a cambio acepta el riesgo de heads divergentes
(ver [`07-decisiones-y-pendientes.md`](07-decisiones-y-pendientes.md)).

## Cómo se ve un request completo

```
1. El navegador pide  GET /oc/OC-2026-000123
2. El transformador ejecuta el frontmatter de la página Astro
3. → gRPC  PurchasingService.GetPurchaseOrder(short_code="OC-2026-000123")
4. El dominio: servicer → controller → use case → repositorio → Postgres
5. El dominio devuelve el mensaje proto
6. Astro renderiza la página con esos datos y la devuelve como HTML
7. El navegador la muestra. Cero JavaScript de framework.
```

Y una mutación:

```
1. El usuario envía  <form method="POST" action={actions.approveOrder}>
2. El Action del transformador recibe { id, reason }
3. → gRPC  PurchasingService.ApprovePurchaseOrder(...)
4. El dominio valida (motivo ≥10 palabras), muta, registra en el change log
5. El Action devuelve el fragmento HTML ya renderizado
6. El script del cliente lo intercambia en el DOM por su target
```

## Escalado

| Dimensión | Cómo escala |
|---|---|
| Un dominio con más carga | Subir `max_workers` hasta el techo del pool. Después, más procesos con puertos distintos y balanceo del lado del cliente. |
| Más dominios | Uno nuevo = una carpeta, un puerto, una entrada en el compose. Nada que tocar en los existentes. |
| El transformador | Varias instancias. **Requiere pub/sub para el fan-out del SSE** — sin eso, un cliente conectado a la instancia A no recibe eventos que llegaron a la B. |
| La base de datos | Vertical primero. El presupuesto de conexiones es el límite real, no el CPU — ver [`04-base-de-datos.md`](04-base-de-datos.md). |

## Dominios de fallo

| Cae | Consecuencia |
|---|---|
| Un dominio | Las pantallas que dependen de él fallan. El resto sigue. |
| El transformador | **Todo el frontend queda inaccesible.** Es el punto único de entrada; con una sola instancia es punto único de fallo. |
| La base de datos | Todo cae. Destino compartido, inherente a tener una sola instancia. |
| El CLI Typer | Nada. Solo se usa para operar, no está en el camino de ningún request. |

## Lo que esta arquitectura NO es

| No es | Por qué importa la distinción |
|---|---|
| Microservicios con autonomía de datos | Comparten base. Un dominio no puede desplegar un cambio de schema sin coordinar. |
| Un monolito | Son procesos separados, con despliegue y dominio de fallo propios. |
| Un sistema distribuido | Sin llamadas entre servicios no hay consistencia eventual, ni sagas, ni transacciones distribuidas. |
| Una API pública | Los dominios no están expuestos. Solo el transformador ve internet. |
