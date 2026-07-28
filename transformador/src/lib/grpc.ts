/**
 * Clientes gRPC hacia los dominios.
 *
 * Es la ÚNICA forma en que el transformador habla con los dominios. Un cliente por
 * dominio, creado una vez por proceso (el canal HTTP/2 es de larga vida y multiplexa
 * todos los requests).
 *
 * Nota de topología: como el transformador abre UNA conexión por dominio y multiplexa
 * todo por ahí, correr varios procesos del dominio con SO_REUSEPORT no reparte carga
 * (reparte conexiones, no requests). Ver 02-dominio-backend.md.
 */

import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

/** Raíz de los .proto, que proto-loader lee en runtime.
 *
 *  No se puede derivar de import.meta.url a secas: en dev este archivo está en
 *  src/lib/, pero en el bundle queda en dist/server/chunks/, así que el mismo
 *  '../../proto' apunta a dos sitios distintos. Se fija con PROTO_ROOT (ver el
 *  compose) y el cálculo relativo queda solo como fallback para dev. */
const PROTO_ROOT =
  process.env.PROTO_ROOT ??
  path.join(path.dirname(fileURLToPath(import.meta.url)), '../../proto');

/** Deadline por defecto. Todas las llamadas llevan uno: sin deadline, un dominio
 *  colgado cuelga al transformador y de ahí al navegador. */
export const DEADLINE_MS = Number(process.env.GRPC_DEADLINE_MS ?? 3000);

export function deadline(ms = DEADLINE_MS): grpc.CallOptions {
  return { deadline: Date.now() + ms };
}

const LOADER_OPTS: protoLoader.Options = {
  keepCase: false,      // snake_case del proto → camelCase en TS
  longs: String,        // int64 como string: no pierde precisión
  enums: String,
  defaults: true,
  oneofs: true,
  includeDirs: [PROTO_ROOT],
};

function loadService(protoPath: string, fullName: string) {
  const def = protoLoader.loadSync(path.join(PROTO_ROOT, protoPath), LOADER_OPTS);
  const pkg = grpc.loadPackageDefinition(def) as any;
  return fullName.split('.').reduce((acc, part) => acc[part], pkg);
}

function client(protoPath: string, fullName: string, hostEnv: string) {
  const host = process.env[hostEnv];
  if (!host) throw new Error(`Falta la variable de entorno ${hostEnv}`);

  const Service = loadService(protoPath, fullName);
  return new Service(host, grpc.credentials.createInsecure(), {
    // Sin reintentos automáticos: una mutación reintentada sin clave de idempotencia
    // duplica. Los reintentos se deciden por caso, no globalmente.
    'grpc.enable_retries': 0,
    'grpc.keepalive_time_ms': 30_000,
  });
}

/** Promisifica un método unario del cliente generado por proto-loader. */
export function unary<Req, Res>(
  service: any,
  method: string,
): (req: Req, opts?: grpc.CallOptions) => Promise<Res> {
  return (req, opts = deadline()) =>
    new Promise<Res>((resolve, reject) => {
      service[method](req, opts, (err: grpc.ServiceError | null, res: Res) =>
        err ? reject(err) : resolve(res),
      );
    });
}

// ── Un cliente por dominio ───────────────────────────────────────────────────
// Agregar acá cada dominio nuevo. El host viene de una variable de entorno para que
// docker compose y el despliegue apunten donde corresponda.

const ejemploService = client(
  'ejemplo/v1/ejemplo.proto',
  'ejemplo.v1.EjemploService',
  'EJEMPLO_GRPC_HOST',
);

export const ejemplo = {
  getEjemplo: unary<{ id: string }, any>(ejemploService, 'GetEjemplo'),
  listEjemplos: unary<any, any>(ejemploService, 'ListEjemplos'),
  confirmarEjemplo: unary<any, any>(ejemploService, 'ConfirmarEjemplo'),
};

const webhookService = client(
  'shared/v1/webhook.proto',
  'shared.v1.WebhookService',
  'EJEMPLO_GRPC_HOST',
);

export const webhooks = {
  handleInbound: unary<
    { provider: string; path: string; headers: Record<string, string>; rawBody: Uint8Array },
    { httpStatus: number; body: Uint8Array }
  >(webhookService, 'HandleInbound'),
};
