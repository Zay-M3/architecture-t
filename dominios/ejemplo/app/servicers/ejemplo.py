"""Servicer de ejemplo: la capa de ENTRADA gRPC.

Delgado por diseño: deserializar el mensaje, llamar al controller, serializar la
respuesta. **Sin lógica de negocio, sin try/except** — el manejo de errores vive en el
controller, que es el único lugar que traduce excepciones de dominio a StatusCode.

Es el equivalente a un router de FastAPI.
"""

# Descomentar cuando existan los stubs (oc proto gen):
# from app.grpc_gen.ejemplo.v1 import ejemplo_pb2, ejemplo_pb2_grpc


# class EjemploServicer(ejemplo_pb2_grpc.EjemploServiceServicer):
class EjemploServicer:
    def __init__(self, controller) -> None:
        self._controller = controller

    def GetEjemplo(self, request, context):
        data = self._controller.get(request.id, context)
        # return ejemplo_pb2.Ejemplo(**data)
        return data

    def ListEjemplos(self, request, context):
        items, total = self._controller.list(
            page=request.page or 1,
            page_size=request.page_size or 50,
            estados=list(request.estados),
            search=request.search,
            context=context,
        )
        # return ejemplo_pb2.ListEjemplosResponse(items=items, total=total)
        return items, total

    def ConfirmarEjemplo(self, request, context):
        data = self._controller.confirmar(
            ejemplo_id=request.id,
            motivo=request.motivo,
            actor_user_id=request.actor_user_id,
            actor_user_name=request.actor_user_name,
            context=context,
        )
        # return ejemplo_pb2.Ejemplo(**data)
        return data
