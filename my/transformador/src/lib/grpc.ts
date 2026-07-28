import * as grpc from "@grpc/grpc-js";
import * as protoLoader from "@grpc/proto-loader";
import path from "node:path";
import { promisify } from "node:util";

const PROTO_ROOT = import.meta.env.PROTO_ROOT ?? '/app/proto';


export const DEADLINE_MS = 3000;

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
    // el loadsync regresa un mapa de nombres y con full name podemos obtener la definición del servicio que queremos, solo es ponerle un as any para que no se queje el compilador
    const def = protoLoader.loadSync(path.join(PROTO_ROOT, protoPath), LOADER_OPTS);
    // Extraer de def la definición del servicio correspondiente a fullName
    return grpc.makeGenericClientConstructor(def[fullName] as any, fullName);
}

function client(protoPath: string, fullName: string, hostEnv: string) {
    const Service = loadService(protoPath, fullName);
    return new Service(hostEnv, grpc.credentials.createInsecure(), {
    'grpc.enable_retries': 0,
    'grpc.keepalive_time_ms': 30_000,
    });
}


const todoService = client(
    'todo/v1/todo.proto',
    'todo.v1.TodoService',
    process.env.TODO_GRPC_HOST ?? 'localhost:50051',
);
//usando promisfy nos quitamos de encima resolver promesas, muchos de los métodos de grpc-js usan callbacks, y promisify nos permite usar async/await
// listTodo en minúscula: proto-loader registra el alias camelCase del rpc ListTodo.
export const todo = {
    listTodo: promisify(todoService.listTodo.bind(todoService)),
};