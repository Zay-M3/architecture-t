/**
 * Health check del transformador. Lo consume el HEALTHCHECK del contenedor y el
 * balanceador.
 *
 * NO chequea los dominios a propósito: si un dominio está caído, el transformador
 * sigue sano y tiene que seguir sirviendo las pantallas que no dependen de él.
 * Mezclar los dos haría que un dominio caído saque de rotación al transformador
 * entero.
 */

import type { APIRoute } from 'astro';

export const GET: APIRoute = () =>
  new Response(JSON.stringify({ status: 'ok' }), {
    status: 200,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  });

export const prerender = false;
