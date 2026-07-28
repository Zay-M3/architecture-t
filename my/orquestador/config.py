from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class Domain:
    name: str
    path: Path
    grpc_port: int
    
DOMAINS: tuple[Domain, ...] = (
    Domain(name="todo", path=ROOT / "dominios/todo", grpc_port=50051),
    # Domain(name="compras", path=ROOT / "dominios/compras", grpc_port=50052),
)


TRANSFORMER_PATH = ROOT / "transformador"

# docker compose y alembic no se ejecutan desde donde uno esté parado: cada uno tiene
# su archivo de configuración en un directorio fijo del repo.
ORCHESTRATOR_PATH = ROOT / "orquestador"
DOCKER_FILE = ROOT / "docker/Dockerfile"

TYPE_CHECKER = "ty"



def domain_by_name(name: str) -> Domain:
    for d in DOMAINS:
        if d.name == name:
            return d
    disponibles = ", ".join(d.name for d in DOMAINS)
    raise SystemExit(f"dominio '{name}' no existe. Disponibles: {disponibles}")


def selected(name: str | None) -> tuple[Domain, ...]:
    return (domain_by_name(name),) if name else DOMAINS

