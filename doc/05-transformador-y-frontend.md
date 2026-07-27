# 05 — Transformador y frontend

> El transformador es el servidor de Astro. Es la única puerta desde internet: llama a
> los dominios por gRPC, renderiza HTML en el servidor, sostiene el canal SSE y tunela
> los webhooks de terceros. **No tiene lógica de negocio.**

## Stack

| Pieza | Elección | Estado |
|---|---|---|
| Framework | **Astro** con `output: 'server'` | decidido |
| Adapter | **`@astrojs/node`** en modo `standalone` | oficial, mantenido, hecho para contenedores |
| Runtime | **Node** | ver la nota sobre Bun más abajo |
| Cliente gRPC | `@grpc/grpc-js` + `@grpc/proto-loader` | sobre Node es la implementación de referencia |
| Framework de cliente | **ninguno** | sin Preact, sin React |
| Gestor de paquetes | Bun (`bun install`, `bun test`) | soportado oficialmente por Astro |

### La nota sobre Bun

La intención original era que el transformador corriera sobre Bun. El estado real,
verificado:

- Astro documenta oficialmente Bun **para el toolchain**: `bun create astro`,
  `bun install`, `bun run dev`, `bun run build`, `bun test`. Eso funciona y se usa.
- **No hay adapter oficial de Bun.** Los oficiales son cloudflare, netlify, node,
  vercel. El comunitario `@nurodev/astro-bun` no tiene release desde 2025-11-25.
- La propia guía de Bun dice: *"By default, Bun runs the dev server with Node.js. To
  use the Bun runtime instead, pass the `--bun` flag"* — o sea, **correr Astro sobre
  Bun es opt-in explícito**, no el camino por defecto. Y esa guía solo cubre
  `astro dev`, nada de producción.

**Decisión:** se arranca con `@astrojs/node` sobre Node, que está soportado de punta a
punta. Bun se queda como gestor de paquetes y test runner. Si alguien verifica que
`bun ./dist/server/entry.mjs` sirve SSR correctamente contra la versión de Astro que
usemos, cambiar es una línea en la config y no toca ni las plantillas ni el proto.

La prueba, cuando se quiera hacer:

```bash
bun run build
node ./dist/server/entry.mjs   # ✅ soportado
bun  ./dist/server/entry.mjs   # ⬅️ lo que hay que verificar
```

## Interactividad sin framework de cliente

Los componentes `.astro` renderizan a HTML sin runtime en el navegador. Los handlers
estilo JSX **no funcionan** — la documentación de Astro es explícita:

```astro
<!-- ❌ Esto no hace nada -->
<button onClick={handleClick}>No pasa nada al hacer clic</button>
```

La interactividad sale de tres mecanismos, y cada uno tiene su lugar:

| Mecanismo | Para qué | JS que envía |
|---|---|---|
| **Astro Actions** | Mutaciones: crear, editar, aprobar, enviar, cancelar | cero con `<form>` |
| **`<script>` + Web Components** | Interacción local: subtotal en vivo, contador de palabras, abrir un modal | mínimo, propio |
| **SSE** | Actualizaciones que el usuario no provocó | el glue, una vez |

### Actions: las mutaciones

Con un `<form>`, cero JavaScript y funciona incluso sin JS habilitado:

```astro
---
import { actions } from 'astro:actions';
---
<form method="POST" action={actions.approvePurchaseOrder}>
  <input type="hidden" name="id" value={order.id} />
  <textarea name="reason" required></textarea>
  <button>Aprobar</button>
</form>
```

```ts
// src/actions/index.ts
import { defineAction, ActionError } from 'astro:actions';
import { z } from 'astro:schema';
import { purchasing } from '../lib/grpc';

export const server = {
  approvePurchaseOrder: defineAction({
    accept: 'form',
    input: z.object({ id: z.string(), reason: z.string() }),
    handler: async ({ id, reason }, ctx) => {
      try {
        const order = await purchasing.approvePurchaseOrder({
          id, reason,
          actorUserId: ctx.locals.user.id,
          actorUserName: ctx.locals.user.name,
        });
        return renderFragment('#oc-header', 'replace', OcHeader, { order });
      } catch (e) {
        throw toActionError(e);   // StatusCode gRPC → ActionError
      }
    },
  }),
};
```

Para las transiciones de estado de una OC — aprobar, enviar, cerrar, cancelar,
archivar — este patrón es **mejor** que un componente de framework: el motivo con ≥10
palabras lo valida el dominio y el error vuelve en el re-render, sin estados de
loading ni manejo de fetch a mano.

### `<script>` + Web Components: la interacción local

El patrón que recomienda Astro, pasando datos del servidor por `data-*`:

```astro
<oc-line-total data-lines={JSON.stringify(lines)}>
  <span class="total">{formatted}</span>
</oc-line-total>

<script>
  class OcLineTotal extends HTMLElement {
    connectedCallback() {
      this.querySelectorAll('input[name^="qty"]').forEach(i =>
        i.addEventListener('input', () => this.recalc())
      );
    }
    recalc() { /* multiplicación local, sin round-trip */ }
  }
  customElements.define('oc-line-total', OcLineTotal);
</script>
```

**Regla de reparto:** la aritmética pura queda local (es una multiplicación, 10
líneas, y evita 50–200 ms de lag por tecla). Todo lo que el servidor **decide** —
validaciones, reglas de estado, el total que se va a persistir — va por Action.

## El contrato de fragmentos

Toda actualización parcial del DOM usa el mismo shape, sin importar si llega por
respuesta de Action o por SSE. **Esto es lo importante de acordar desde el día uno**:
el transporte es intercambiable, el contrato no.

```ts
type FragmentUpdate = {
  target: string;                          // selector CSS: "#oc-123-lines"
  action: 'replace' | 'update' | 'append' | 'prepend' | 'remove' | 'before' | 'after';
  html: string;
};
```

El vocabulario es el de **Turbo Streams** (Hotwire), deliberadamente: está probado y
no hay razón para inventar otro.

El glue del cliente, escrito una vez para toda la aplicación:

```ts
// src/scripts/swap.ts
export function applyFragment({ target, action, html }: FragmentUpdate) {
  const el = document.querySelector(target);
  if (!el) return;
  const frag = document.createRange().createContextualFragment(html);
  switch (action) {
    case 'replace': el.replaceWith(frag); break;
    case 'update':  el.replaceChildren(frag); break;
    case 'append':  el.append(frag); break;
    case 'prepend': el.prepend(frag); break;
    case 'before':  el.before(frag); break;
    case 'after':   el.after(frag); break;
    case 'remove':  el.remove(); break;
  }
}
```

Los fragmentos se renderizan con la **Container API** de Astro, que permite renderizar
un componente a string fuera de un request de página:

```ts
import { experimental_AstroContainer } from 'astro/container';

const container = await experimental_AstroContainer.create();
const html = await container.renderToString(OcLineRow, {
  props: { line },
  partial: true,          // sin el shell del documento
});
```

> **Caveat:** el prefijo `experimental_` está en el nombre de la API. Puede cambiar
> entre versiones menores de Astro, y cada fragmento pasa por ahí. Pinear la versión de
> Astro y leer el changelog en cada bump.

## SSE

El canal server → navegador. Va desde el día uno porque es una **capacidad de la
plataforma**, no una feature de un dominio: los dominios que se sumen después van a
necesitarla y tiene que estar.

```ts
// src/pages/events.ts
export const GET: APIRoute = async ({ locals, request }) => {
  const stream = new ReadableStream({
    start(controller) {
      const send = (u: FragmentUpdate) =>
        controller.enqueue(`data: ${JSON.stringify(u)}\n\n`);

      const unsubscribe = bus.subscribe(locals.user.id, send);

      // keep-alive: sin esto el ALB corta la conexión al minuto
      const ping = setInterval(() => controller.enqueue(': ping\n\n'), 30_000);

      request.signal.addEventListener('abort', () => {
        clearInterval(ping);
        unsubscribe();
      });
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
};
```

### Tres requisitos que no son opcionales

1. **Keep-alive cada ~30 s.** El idle timeout del ALB son 60 s por defecto. Sin pings,
   la conexión se corta sola y produce el clásico "se desconecta y no sé por qué".
2. **HTTP/2 en el ingress.** Sobre HTTP/1.1 el navegador permite 6 conexiones por
   origen y SSE ocupa una permanentemente: con varias pestañas abiertas la aplicación
   se traba. Sobre HTTP/2 va multiplexado.
3. **Pub/sub para el fan-out.** El registro de suscripciones en memoria funciona con
   **una** instancia del transformador. Con dos detrás de un balanceador, un cliente
   conectado a A no recibe eventos que llegaron a B — en silencio. El bus (Dragonfly /
   Redis pub/sub) es lo que lo arregla, y va desde el principio si se planea más de una
   instancia.

### Qué va por SSE y qué no

| Situación | Canal |
|---|---|
| El usuario actúa y ve su propio resultado | **La respuesta del Action.** Un hop, sincrónico. |
| Otro operador cambia algo que estás viendo | SSE |
| El almacén registra una recepción mientras compras mira | SSE |
| Un job asíncrono termina (OCR, importación) | SSE |
| Alertas de vencimientos | SSE |

Rutear el resultado del propio usuario por SSE serían tres hops donde alcanza uno, y
mete una carrera: la respuesta del Action llega antes que el push.

### Reconexión

El navegador reconecta solo y manda `Last-Event-ID`. Lo más simple y suficiente: al
reconectar, el cliente refetchea el estado de la página. Implementar replay de eventos
solo si aparece una razón concreta.

## Cliente gRPC

```ts
// src/lib/grpc.ts
import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';

const def = protoLoader.loadSync('proto/purchasing/v1/purchasing.proto', {
  keepCase: false, longs: String, enums: String, defaults: true, oneofs: true,
});
const pkg = grpc.loadPackageDefinition(def) as any;

export const purchasing = new pkg.purchasing.v1.PurchasingService(
  process.env.PURCHASING_GRPC_HOST!,
  grpc.credentials.createInsecure(),   // TLS lo termina el balanceador interno
);
```

Con **deadline en cada llamada** y sin reintentos automáticos en mutaciones (una
mutación reintentada sin clave de idempotencia duplica):

```ts
const DEADLINE_MS = 3000;
function deadline() { return { deadline: Date.now() + DEADLINE_MS }; }
```

## Webhooks tunelados

El transformador es el único con HTTP, así que recibe los webhooks de terceros y los
reenvía crudos por gRPC. **No valida firmas** — eso lo hace el dominio, que es donde
viven los secretos de proveedor.

```ts
// src/pages/webhooks/[provider].ts
export const POST: APIRoute = async ({ params, request }) => {
  const raw = new Uint8Array(await request.arrayBuffer());   // CRUDO, sin parsear
  const headers = Object.fromEntries(request.headers.entries());

  const res = await webhookClient.handleInbound({
    provider: params.provider,
    path: new URL(request.url).pathname,
    headers,
    rawBody: raw,
  });

  return new Response(res.body, { status: res.httpStatus });
};
```

Si el body se deserializa y se reserializa, la firma de Meta (`X-Hub-Signature-256`,
calculada sobre los bytes exactos) no valida nunca.

## Navegación

`<ClientRouter />` en el layout compartido. Sin eso, cada navegación es una recarga
completa y en una aplicación de gestión se siente mal.

```astro
---
import { ClientRouter } from 'astro:transitions';
---
<head>
  <ClientRouter />
</head>
```

> **Gotcha verificado:** con View Transitions **los scripts no se re-ejecutan** en cada
> navegación. Para el `EventSource` de SSE eso es conveniente — sobrevive la navegación
> y no se reconstruye. Pero si un handler cachea nodos del DOM, después del swap apuntan
> a nodos desprendidos. Se evita resolviendo el selector **en el momento del mensaje**,
> como hace `applyFragment`. Si hace falta re-bindear algo, el hook es
> `astro:page-load`.

## Sobre Preact

**No se usa.** El CRM actual sigue en Preact y no se toca, pero acá no entra.

La puerta queda entreabierta para un solo caso: reutilizar un componente que ya exista
en el CRM. Si aparece, se monta como isla y ese componente sigue haciendo su fetch como
lo hace hoy. Pero es la excepción, no la vía.

Vale saber el costo de la regla: un editor de líneas con alta, baja y recálculo en vivo
son ~200 líneas de Web Components contra ~60 con estado de framework. Con SSE y
Actions ese costo baja mucho, porque el recálculo lo hace el servidor y el fragmento
vuelve renderizado — y así el cálculo del total existe **una sola vez**, en el dominio,
en vez de duplicado entre servidor y navegador.
