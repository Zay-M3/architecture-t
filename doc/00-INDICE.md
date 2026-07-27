# Arquitectura de microservicios — v3

> Plataforma nueva. **No migra nada del CRM actual**, que queda como está. Monolito
> modular con dominios como servicios gRPC independientes, una sola base de datos,
> un transformador que renderiza el frontend, y un CLI que orquesta todo.

> **Estado:** diseño cerrado, sin implementar. Un único riesgo abierto (Bun como
> runtime) que no bloquea nada. Lo pendiente está listado sin disimulo en
> [`07-decisiones-y-pendientes.md`](07-decisiones-y-pendientes.md).

## El mapa en una línea

```
[dominio Python + gRPC] ──gRPC──▶ [transformador: Astro SSR] ──HTML + SSE──▶ [cliente]
                                            ▲
                        [CLI Typer] ── docker · alembic · pytest · ruff · type
```

## Orden de lectura

| # | Archivo | Para qué |
|---|---------|----------|
| 01 | [`01-arquitectura.md`](01-arquitectura.md) | El mapa completo, qué es cada pieza y por qué. Empezá acá. |
| 02 | [`02-dominio-backend.md`](02-dominio-backend.md) | Cómo se construye un dominio: capas, `grpcio` sync, DI, interceptores. |
| 03 | [`03-contrato-grpc.md`](03-contrato-grpc.md) | Convenciones de `.proto`, errores, dinero, webhooks tunelados, documentación. |
| 04 | [`04-base-de-datos.md`](04-base-de-datos.md) | Una Postgres, Alembic global, presupuesto de conexiones, dueño de cada tabla. |
| 05 | [`05-transformador-y-frontend.md`](05-transformador-y-frontend.md) | Astro SSR, interactividad sin framework, SSE, contrato de fragmentos. |
| 06 | [`06-orquestador-typer.md`](06-orquestador-typer.md) | El CLI: comandos, migraciones, tests, formato y tipos. |
| 07 | [`07-decisiones-y-pendientes.md`](07-decisiones-y-pendientes.md) | Lo cerrado con su motivo, los riesgos aceptados, lo que falta decidir. |
| — | [`plantillas/`](plantillas/) | Esqueletos para copiar: dominio, transformador, orquestador, proto, docker. |

## Quién lee qué

- **Arquitecto / dueño de producto:** 01 y 07. Ahí está el qué y el qué falta.
- **Backend que arranca un dominio:** 02, 03, 04 y `plantillas/dominio/`.
- **Frontend:** 05 y `plantillas/transformador/`.
- **Quien monta el entorno:** 06, `plantillas/orquestador/` y `plantillas/docker/`.
- **Con tres minutos:** 01, después la tabla de pendientes de 07.

## Decisiones que gobiernan todo el resto

Si solo te llevás cinco cosas de este paquete:

1. **Los dominios hablan gRPC y nada más.** Sin FastAPI, sin HTTP, sin REST.
2. **Una sola base de datos**, compartida por todos los dominios. Alembic global desde el CLI.
3. **Los dominios no se hablan entre sí.** El transformador es el único que los llama.
4. **El frontend no tiene framework de cliente.** Astro renderiza en el servidor; la
   interactividad sale de Actions, `<script>` y Web Components.
5. **El servidor gRPC es sincrónico.** No hay ninguna operación de compras que gane
   con async, y sync perdona los errores que async castiga con el proceso entero.

## Lo que este paquete NO cubre

- **Auth.** Va en un servicio aparte, fuera de este diseño.
- **El CRM Preact actual.** Se queda intacto; nada se migra ni se toca.
- **La lógica de negocio de Órdenes de Compra.** Eso vive en
  [`docs_/ordenes-de-compra/`](../ordenes-de-compra/) y se diseña sobre este andamio.

## Historial

`_v1-descartado/` contiene la versión anterior del paquete: microservicio con base
de datos propia, gRPC bidireccional, espejos de catálogo, outbox, RS256 y FastAPI en
los dominios. **Nada de eso aplica.** Queda solo como contraste de por qué el diseño
actual es más simple.
