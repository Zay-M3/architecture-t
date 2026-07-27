/**
 * Traducción de errores: grpc.StatusCode -> ActionError de Astro (y de ahí a HTTP).
 *
 * El dominio ya decidió la semántica del error con su StatusCode. Acá no se
 * reinterpreta: se traduce. Tabla completa en 03-contrato-grpc.md.
 */

import { ActionError } from 'astro:actions';
import * as grpc from '@grpc/grpc-js';

const STATUS_TO_ACTION: Record<number, ActionError['code']> = {
  [grpc.status.NOT_FOUND]: 'NOT_FOUND',
  [grpc.status.ALREADY_EXISTS]: 'CONFLICT',
  [grpc.status.INVALID_ARGUMENT]: 'BAD_REQUEST',
  [grpc.status.FAILED_PRECONDITION]: 'CONFLICT',
  [grpc.status.PERMISSION_DENIED]: 'FORBIDDEN',
  [grpc.status.UNAUTHENTICATED]: 'UNAUTHORIZED',
  [grpc.status.UNAVAILABLE]: 'SERVICE_UNAVAILABLE',
  [grpc.status.DEADLINE_EXCEEDED]: 'SERVICE_UNAVAILABLE',
  [grpc.status.RESOURCE_EXHAUSTED]: 'TOO_MANY_REQUESTS',
};

export function toActionError(err: unknown): ActionError {
  const e = err as grpc.ServiceError;

  if (typeof e?.code === 'number') {
    const code = STATUS_TO_ACTION[e.code] ?? 'INTERNAL_SERVER_ERROR';
    // `details` es el mensaje que puso el dominio en context.abort().
    return new ActionError({ code, message: e.details || e.message });
  }

  // Cualquier otra cosa: no filtrar el detalle al cliente, pero dejarlo en el log.
  console.error('error no-gRPC en un Action', err);
  return new ActionError({
    code: 'INTERNAL_SERVER_ERROR',
    message: 'Error interno',
  });
}

/** Para rutas de página (no Actions): StatusCode -> HTTP. */
export function toHttpStatus(err: unknown): number {
  const e = err as grpc.ServiceError;
  switch (e?.code) {
    case grpc.status.NOT_FOUND: return 404;
    case grpc.status.ALREADY_EXISTS: return 409;
    case grpc.status.INVALID_ARGUMENT: return 422;
    case grpc.status.FAILED_PRECONDITION: return 409;
    case grpc.status.PERMISSION_DENIED: return 403;
    case grpc.status.UNAUTHENTICATED: return 401;
    case grpc.status.UNAVAILABLE:
    case grpc.status.DEADLINE_EXCEEDED: return 503;
    default: return 500;
  }
}
