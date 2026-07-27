/**
 * Endpoint SSE: el canal servidor -> navegador.
 *
 * Tres requisitos que NO son opcionales (ver 05-transformador-y-frontend.md):
 *
 *  1. Keep-alive cada ~30 s. El idle timeout del balanceador son 60 s por defecto; sin
 *     pings la conexión se corta sola y produce el clásico "se desconecta y no sé por
 *     qué".
 *  2. HTTP/2 en el ingress. Sobre HTTP/1.1 el navegador permite 6 conexiones por origen
 *     y SSE ocupa una permanentemente: con varias pestañas la aplicación se traba.
 *  3. Pub/sub para el fan-out. El registro en memoria funciona con UNA instancia del
 *     transformador. Con dos detrás del balanceador, un cliente conectado a A no recibe
 *     lo que llegó a B, en silencio.
 */

import type { APIRoute } from 'astro';
import { subscribe } from '../lib/bus';

const KEEPALIVE_MS = 30_000;

export const GET: APIRoute = ({ request, locals }) => {
  const userId = (locals as any).userId ?? 'anon';   // auth va en otro servicio

  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();
      const send = (payload: unknown) =>
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(payload)}\n\n`));

      const unsubscribe = subscribe(userId, send);

      // Requisito 1: sin esto el balanceador corta la conexión al minuto.
      const ping = setInterval(
        () => controller.enqueue(encoder.encode(': ping\n\n')),
        KEEPALIVE_MS,
      );

      request.signal.addEventListener('abort', () => {
        clearInterval(ping);
        unsubscribe();
        try { controller.close(); } catch { /* ya cerrado */ }
      });
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
      // Evita que un proxy intermedio buffere el stream y lo vuelva inútil.
      'X-Accel-Buffering': 'no',
    },
  });
};
