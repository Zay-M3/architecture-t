"""Registro de dominios.

Agregar un dominio es una línea acá: los comandos del CLI lo recogen solos.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Domain:
    name: str
    path: str
    grpc_port: int


DOMAINS: tuple[Domain, ...] = (
    Domain(name="ejemplo", path="dominios/ejemplo", grpc_port=50051),
    # Domain(name="compras", path="dominios/compras", grpc_port=50052),
)

TRANSFORMER_PATH = "transformador"

# Cambiar por "mypy" o "pyright" según lo que se elija.
# Si es `ty` (de Astral): es pre-1.0, conviene correrlo junto a mypy o pyright un
# tiempo antes de dejarlo como único gate. Ver 07, P7.
TYPE_CHECKER = "ty"


def domain_by_name(name: str) -> Domain:
    for d in DOMAINS:
        if d.name == name:
            return d
    disponibles = ", ".join(d.name for d in DOMAINS)
    raise SystemExit(f"dominio '{name}' no existe. Disponibles: {disponibles}")


def selected(name: str | None) -> tuple[Domain, ...]:
    return (domain_by_name(name),) if name else DOMAINS
