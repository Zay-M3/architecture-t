/**
 * Bus de eventos para el fan-out del SSE.
 *
 * Dos implementaciones, y la elección NO es de comodidad:
 *
 *  - `memory`: funciona solo con UNA instancia del transformador. Con dos detrás de un
 *    balanceador, un cliente conectado a la instancia A no recibe eventos que llegaron
 *    a la B, y falla en SILENCIO: nadie ve un error, simplemente la pantalla no se
 *    actualiza.
 *  - `redis`: pub/sub sobre Dragonfly (compatible con el protocolo de Redis). Es lo que
 *    permite escalar el transformador horizontalmente.
 *
 * Por eso SSE "entra con pub/sub o no entra": sin el bus, agregar una segunda instancia
 * rompe el push sin avisar.
 *
 * Pendiente: el rol de Dragonfly no está cerrado (ver 07, P3). Esta plantilla asume
 * que se usa como bus; si además se usa como cache, es la misma instancia.
 */

type Send = (payload: unknown) => void;

const CHANNEL = 'fragments';

// ── En memoria: para desarrollo y una sola instancia ─────────────────────────
const local = new Map<string, Set<Send>>();

function subscribeLocal(userId: string, send: Send): () => void {
  const set = local.get(userId) ?? new Set<Send>();
  set.add(send);
  local.set(userId, set);
  return () => {
    set.delete(send);
    if (set.size === 0) local.delete(userId);
  };
}

function publishLocal(userId: string, payload: unknown): void {
  local.get(userId)?.forEach((send) => send(payload));
}

// ── Redis / Dragonfly: para más de una instancia ─────────────────────────────
const REDIS_URL = process.env.REDIS_URL;

let publisher: any = null;
let subscriber: any = null;

async function initRedis() {
  if (!REDIS_URL || subscriber) return;
  const { default: Redis } = await import('ioredis');
  publisher = new Redis(REDIS_URL);
  subscriber = new Redis(REDIS_URL);

  await subscriber.subscribe(CHANNEL);
  subscriber.on('message', (_channel: string, raw: string) => {
    const { userId, payload } = JSON.parse(raw);
    // Cada instancia entrega solo a los clientes que tiene conectados.
    publishLocal(userId, payload);
  });
}

// ── API pública ──────────────────────────────────────────────────────────────

export function subscribe(userId: string, send: Send): () => void {
  void initRedis();
  return subscribeLocal(userId, send);
}

export async function publish(userId: string, payload: unknown): Promise<void> {
  if (REDIS_URL) {
    await initRedis();
    await publisher.publish(CHANNEL, JSON.stringify({ userId, payload }));
    return;   // vuelve por el canal y se entrega en TODAS las instancias
  }
  publishLocal(userId, payload);
}
