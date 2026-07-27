/**
 * Túnel de webhooks de terceros.
 *
 * El transformador es el único con HTTP, así que recibe los POST de Twilio, Meta,
 * Shopify y Sendcloud. Pero NO valida firmas ni interpreta payloads: reenvía los bytes
 * crudos por gRPC al dominio dueño, que tiene el secreto.
 *
 * Así los secretos de proveedor se quedan en Python y no se mudan a un segundo runtime.
 *
 * Ver 03-contrato-grpc.md.
 */

import type { APIRoute } from 'astro';
import { webhooks, deadline } from '../../lib/grpc';

/** Proveedores aceptados. Lista cerrada: un provider desconocido es 404, no un passthrough. */
const PROVIDERS = new Set(['twilio', 'meta', 'shopify', 'sendcloud']);

/** Los webhooks pueden tardar más que una llamada normal. */
const WEBHOOK_DEADLINE_MS = 10_000;

export const POST: APIRoute = async ({ params, request }) => {
  const provider = params.provider ?? '';
  if (!PROVIDERS.has(provider)) {
    return new Response('proveedor desconocido', { status: 404 });
  }

  // CRUDO. Meta firma sobre estos bytes exactos con X-Hub-Signature-256: si acá se
  // parsea el JSON y se vuelve a serializar, cambia el orden de claves y el espaciado,
  // y la firma NO valida nunca.
  const rawBody = new Uint8Array(await request.arrayBuffer());
  const headers = Object.fromEntries(request.headers.entries());

  try {
    const res = await webhooks.handleInbound(
      { provider, path: new URL(request.url).pathname, headers, rawBody },
      deadline(WEBHOOK_DEADLINE_MS),
    );

    // El status lo decide el DOMINIO. Twilio y Meta reintentan ante cualquier cosa que
    // no sea 2xx, así que inventarlo acá cambiaría su comportamiento de reintentos.
    return new Response(res.body?.length ? Buffer.from(res.body) : null, {
      status: res.httpStatus || 200,
    });
  } catch (err) {
    // 503 a propósito: le dice al proveedor "reintentá", que es lo correcto si el
    // dominio está caído. Un 200 acá perdería el evento para siempre.
    console.error(`webhook ${provider} falló`, err);
    return new Response('dominio no disponible', { status: 503 });
  }
};

export const prerender = false;
