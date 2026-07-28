"""Servicer de todo: la capa de ENTRADA gRPC.

Delgado por diseño: deserializar el mensaje, llamar al controller, serializar la
respuesta. **Sin lógica de negocio, sin try/except** — el manejo de errores vive en el
controller, que es el único lugar que traduce excepciones de dominio a StatusCode.

Es el equivalente a un router de FastAPI.
"""

from app.grpc_gen.todo.v1 import todo_pb2, todo_pb2_grpc


def _to_proto(t) -> todo_pb2.Todo:
    """Fila de la base → mensaje del contrato."""
    msg = todo_pb2.Todo(
        id=t.id,
        codigo=t.codigo,
        estado=t.estado,
        nombre=t.nombre,
        created_by_user_id=t.created_by_user_id,
        created_by_user_name=t.created_by_user_name,
    )
    # Timestamp no se asigna con `=`: es un submensaje, se rellena.
    msg.created_at.FromDatetime(t.created_at)
    return msg


class TodoService(todo_pb2_grpc.TodoServiceServicer):
    def __init__(self, controller) -> None:
        self._controller = controller

    def ListTodo(self, request, context):
        items, _total = self._controller.list(
            page=request.page or 1,
            page_size=request.page_size or 50,
            estados=list(request.estados),
            nombre=request.nombre,
            context=context,
        )

        return todo_pb2.ListTodoResponse(
            items=[_to_proto(t) for t in items],
            # El contrato declara `nombre` en la respuesta, no `total`: se devuelve
            # el filtro aplicado. Si algún día quieres paginar de verdad, esto pasa
            # a ser `int32 total = 2` en el .proto.
            nombre=request.nombre,
        )
