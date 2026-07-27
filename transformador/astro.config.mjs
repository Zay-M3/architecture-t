import { defineConfig } from 'astro/config';
import node from '@astrojs/node';

// @astrojs/node en modo standalone genera dist/server/entry.mjs, que es un servidor
// HTTP real. Es el adapter OFICIAL para self-hosted y está pensado para contenedores.
//
// Sobre Bun: no hay adapter oficial de Bun (los oficiales son cloudflare, netlify,
// node, vercel) y el comunitario @nurodev/astro-bun no tiene release desde 2025-11-25.
// La guía de Bun además aclara que por defecto Astro corre sobre Node incluso cuando
// se lo invoca con `bun`. Así que se arranca con Node, que está soportado de punta a
// punta, y si alguien verifica que `bun ./dist/server/entry.mjs` sirve SSR bien, el
// cambio es solo el comando de arranque — este archivo no se toca.
//
// Ver 05-transformador-y-frontend.md y 07 P11.

export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),

  server: {
    host: true,
    port: Number(process.env.PORT ?? 4321),
  },

  // Navegación del lado del cliente. Sin esto cada navegación es recarga completa y
  // en una aplicación de gestión se siente mal.
  //
  // Gotcha: con View Transitions los scripts NO se re-ejecutan en cada navegación.
  // Para el EventSource del SSE eso es conveniente (sobrevive la navegación), pero un
  // handler que cachee nodos del DOM va a apuntar a nodos desprendidos después del
  // swap. Por eso applyFragment() resuelve el selector en el momento del mensaje.
  prefetch: true,

  vite: {
    // El .proto se lee en runtime con proto-loader, no se empaqueta.
    assetsInclude: ['**/*.proto'],
  },
});
