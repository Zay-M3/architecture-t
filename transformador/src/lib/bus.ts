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


// ── API pública ──────────────────────────────────────────────────────────────

export function subscribe(userId: string, send: Send): () => void {
  void initRedis();
  return subscribeLocal(userId, send);
}

export async function publish(userId: string, payload: unknown): Promise<void> {
  publishLocal(userId, payload);
}
