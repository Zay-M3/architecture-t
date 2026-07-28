import * as grpc from '@grpc/grpc-js';
// primera prueba sin SSR
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
