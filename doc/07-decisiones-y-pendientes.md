# 07 — Decisiones, riesgos aceptados y pendientes

## Decisiones cerradas

| # | Decisión | Motivo |
|---|---|---|
| D1 | **Dominios gRPC puros, sin FastAPI** | El único consumidor es el transformador y habla gRPC. Un servidor HTTP sin consumidores es superficie que se mantiene sin usar. Webhooks, health checks y documentación están resueltos sin HTTP. |
| D2 | **Servidor sincrónico** (`ThreadPoolExecutor`) | Ninguna operación del dominio gana con async: son queries secuenciales más PDF, XLSX y Excel, que bloquean. Y el olvido en sync cuesta un hilo ocupado; en async congela el proceso entero. |
| D3 | **Una sola PostgreSQL compartida** | Da transacciones ACID que cruzan dominios y elimina espejos, outbox y compensaciones. |
| D4 | **Alembic global, cadena única, desde el CLI** | Con base compartida y FKs entre dominios hace falta orden determinista. Una cadena lo resuelve por construcción. |
| D5 | **Los dominios no se hablan entre sí** | N dominios hablando entre sí son N² contratos y un grafo de arranque. Con base compartida el dato ya está sin red en medio. |
| D6 | **El ingreso de stock pertenece a compras** | Una orden de compra *es* la entrada de mercadería. Separarlo dibujaría el límite por el medio de una transacción. |
| D7 | **Webhooks tunelados por el transformador** | Es el único con HTTP. Reenvía bytes crudos por gRPC; el dominio valida la firma con su propio secreto, que no se muda a otro runtime. |
| D8 | **Sin streaming bidireccional** | No hay caso de uso, y el navegador no puede hacerlo: gRPC-Web solo soporta unario y, condicionalmente, server-streaming. |
| D9 | **SSE desde el día uno** | Es capacidad de plataforma, no feature de un dominio: los que se sumen después la van a necesitar. Entra con pub/sub, keep-alive y HTTP/2, no sola. |
| D10 | **Astro sin framework de cliente** | El cálculo del total y las reglas existen en el dominio de todas formas. Con estado en el cliente se escriben dos veces y divergen. |
| D11 | **`@astrojs/node` sobre Node** | Es el adapter oficial para self-hosted. No hay adapter oficial de Bun y el comunitario está 8 meses sin release. |
| D12 | **Typer es un CLI, Docker es el process manager** | Un supervisor propio reimplementaría reinicio, health checks y rolling restart, que Docker ya hace. |
| D13 | **Auth fuera de este diseño** | Va en un servicio aparte. |
| D14 | **El CRM Preact actual no se toca** | Implementación nueva, sin migración. |

## Riesgos aceptados

Aceptados **explícitamente**, con la mitigación al lado. No son descuidos.

| Riesgo | Consecuencia si pega | Mitigación |
|---|---|---|
| **Heads divergentes** en la cadena única de Alembic | `upgrade head` falla; en el peor caso un deploy con schema inconsistente | Test de un solo head, **dentro de `oc check`** y en CI |
| **Si cae la base, cae todo** | Plataforma completa fuera de servicio | Inherente a una sola instancia. Backups. |
| **El transformador es punto único de fallo** | Todo el frontend inaccesible aunque los dominios estén sanos | Varias instancias detrás del balanceador — y entonces el pub/sub del SSE deja de ser opcional |
| **Acoplamiento de schema entre dominios** | Un cambio del dueño rompe al lector | Un solo repositorio por tabla ajena + `GRANT SELECT` donde se pueda |
| **Container API marcada `experimental_`** | Un bump de Astro puede romper el render de fragmentos | Pinear la versión de Astro; leer el changelog en cada bump |
| **`autogenerate` viendo tablas ajenas** | Migración que propone borrar tablas de otro dominio | `env.py` importa todos los modelos + leer siempre el diff |

## Pendientes

### Bloquean escribir código

Ninguno. El diseño está cerrado y las plantillas son ejecutables.

### Bloquean dimensionar

| # | Pendiente | Por qué hace falta |
|---|---|---|
| P1 | **Clase de la instancia de PostgreSQL** | Sin eso, el presupuesto de conexiones de [`04`](04-base-de-datos.md) es conservador por precaución, no calculado. Necesario antes de cualquier prueba de carga. |
| P2 | **Objetivo de disponibilidad en número** | "No debe caer" no es dimensionable. Un 99,9 % son ~43 min/mes; un 99,99 % son ~4. Define si hace falta multi-AZ y varias instancias, que es plata. |

### Decisiones de diseño abiertas, con recomendación

| # | Pendiente | Recomendación | Qué cambia |
|---|---|---|---|
| P3 | **Rol de Dragonfly** | Definir qué se cachea, con qué TTL, y qué se devuelve en cache miss con la base caída. Hoy solo está el dato de que se usa vía SDK de Redis en el CRM actual. | Si además va a ser el bus de pub/sub del SSE, entra desde el principio. |
| P4 | **Código compartido entre dominios** (`to_decimal`, `clock`, modelos de tablas comunes) | Un paquete común versionado, no duplicación. | **Es la que decide si esto se mantiene sano a los 6 meses.** Duplicar es rápido y divergente. |
| P5 | **¿Schema propio por dominio (`compras.*`) o todo en `public`?** | Con cadena global, `public`. | Un schema por dominio da claridad de propiedad a costa de `search_path` por sesión. |
| P6 | **¿FKs entre dominios?** | Ponerlas: con cadena global son seguras y dan integridad referencial. | No ponerlas deja los dominios más despegados a costa de referencias huérfanas. |
| P7 | **Type checker** | Si es `ty`, correrlo junto a mypy o pyright hasta que madure. | Es una constante en el CLI; cambiarlo es una línea. |
| P8 | **Namespacear los advisory locks** por dominio | Hacerlo desde el primer job programado. | Con la misma clave, dos dominios que corran jobs se bloquean entre sí. |
| P9 | **Tag `service` en la observabilidad** | Desde el primer dominio. | Sin eso los errores de todos los dominios se mezclan en el mismo proyecto. |
| P10 | **Tablas que dos dominios escriban** | Que no haya ninguna. Si aparece una, revisar si los límites están bien dibujados. | Es la señal de que un dominio está partido por el medio. |

### Verificación pendiente, sin urgencia

| # | Qué | Cómo se resuelve |
|---|---|---|
| P11 | **¿Corre Astro SSR sobre Bun?** | `bun run build` y después `bun ./dist/server/entry.mjs`. Si sirve una página SSR y un Action, se cambia el runtime. Si no, sigue en Node. **No bloquea nada**: arranca con Node y el cambio después es una línea. |
| P12 | **¿Funciona `@grpc/grpc-js` sobre Bun?** | Solo importa si P11 sale bien. Sobre Node es la implementación de referencia, riesgo cero. |

## Lo que hay que estudiar antes de implementar

| Tema | Por qué |
|---|---|
| **Turbo Streams** (Hotwire) | El vocabulario de acciones sobre un target ya está resuelto y probado. El contrato de fragmentos de [`05`](05-transformador-y-frontend.md) lo copia a propósito. |
| **Expand/contract** (parallel change) | Es cómo se cambia un schema compartido sin coordinar despliegues. Con base única y varios dominios, es la técnica que evita el downtime. |
| **Bounded context: cómo se identifican los límites** | Event Storming o Context Mapping. La regla operativa ya está en [`04`](04-base-de-datos.md) — si dos cosas pasan o no pasan juntas, están en el mismo dominio — pero conviene tener el método cuando aparezca el segundo dominio. |
| **Modelo de servidor de gRPC en Python** | Sync con thread pool vs aio, y por qué un bloqueo en aio congela todo. Está resumido en [`02`](02-dominio-backend.md), pero vale leer la fuente antes de cambiar D2. |

## Cómo se retoma esto

1. Leer [`01-arquitectura.md`](01-arquitectura.md).
2. Copiar `plantillas/dominio/` como base del dominio de compras y `plantillas/orquestador/` como CLI.
3. `oc up` y `oc check` en verde con el dominio vacío. **Ese es el hito cero**: el andamio funciona antes de que exista una sola regla de negocio.
4. Recién ahí, diseñar Órdenes de Compra sobre [`docs_/ordenes-de-compra/`](../ordenes-de-compra/).
