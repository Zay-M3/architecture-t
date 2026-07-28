from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


import typer

from config import (
    DOMAINS,
    ORCHESTRATOR_PATH,
    ROOT,
    DOCKER_FILE,
    TRANSFORMER_PATH,
    TYPE_CHECKER,
    domain_by_name,
    selected,
    Domain
)

app = typer.Typer(no_args_is_help=True, help="Orquestador de la plataforma")
db = typer.Typer(no_args_is_help=True, help="Migraciones (cadena única, global)")
proto = typer.Typer(no_args_is_help=True, help="Contratos gRPC")
app.add_typer(db, name="db")
app.add_typer(proto, name="proto")


def _run(cmd: list[str], cwd: str | Path | None = None) -> None:
    typer.secho(f"$ {' '.join(cmd)}", fg=typer.colors.BRIGHT_BLACK)
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _tag(d: Domain) -> str:
    """Nombre de la imagen y del contenedor de un dominio.

    Un solo sitio: lo usan el build, el run, los logs y el down. Repetirlo a mano
    garantiza que algún día uno quede desincronizado.
    """
    return f"dominio-{d.name}"


def _build(d: Domain) -> list[str]:
    """Línea de `docker build` para un dominio."""
    return [
        "docker", "build",
        "-f", str(DOCKER_FILE),
        "--target", "runtime",
        # Relativo al contexto: los COPY del Dockerfile no ven rutas absolutas.
        "--build-arg", f"DOMAIN_PATH={d.path.relative_to(ROOT)}",
        "-t", _tag(d),
        str(ROOT),
    ]


def _start(d: Domain) -> list[str]:
    """Línea de `docker run` para un dominio.

    Dentro del contenedor el servidor siempre escucha en 50051 (es lo que declara el
    EXPOSE). Lo que cambia por dominio es el puerto de FUERA.
    """
    return [
        "docker", "run", "-d",
        "--name", _tag(d),
        "-p", f"{d.grpc_port}:50051",
        _tag(d),
    ]


@app.command()
def up(domain: str | None = None) -> None:
    """Construye y levanta la plataforma (o un dominio)."""
    for d in selected(domain):
        _run(_build(d))
        _run(_start(d))


@app.command()
def down(domain: str | None = None) -> None:
    """Baja la plataforma (o un dominio).

    `rm -f` para y borra en un paso; sin compose no hay un `down` que lo haga solo.
    """
    for d in selected(domain):
        _run(["docker", "rm", "-f", _tag(d)])


@app.command()
def logs(domain: str, follow: bool = True) -> None:
    """Logs de un dominio.

    El dominio es obligatorio: `docker logs` habla con UN contenedor. Compose podía
    multiplexar varios porque él los conocía a todos.
    """
    cmd = ["docker", "logs"]
    if follow:
        cmd.append("-f")
    cmd.append(_tag(domain_by_name(domain)))
    _run(cmd)


@app.command()
def ps() -> None:
    """Estado de los contenedores."""
    _run(["docker", "ps"])


@app.command()
def install(domain: str | None = None) -> None:
    """Instala dependencias: uv en los dominios, bun en el transformador."""
    for d in selected(domain):
        _run(["uv", "sync", "--all-groups"], cwd=d.path)
    if domain is None:
        _run(["bun", "install"], cwd=TRANSFORMER_PATH)


@app.command()
def dev(domain: str) -> None:
    """Levanta un dominio con recarga al guardar.

    gRPC no trae --reload; se envuelve con watchfiles, que es lo que uvicorn usa por
    dentro.
    """
    d = domain_by_name(domain)
    _run(["watchfiles", "python -m app.server", "app/"], cwd=d.path)

def _alembic(*args: str) -> None:
    # alembic.ini vive en orquestador/, no donde el usuario esté parado.
    _run(["alembic", *args], cwd=ORCHESTRATOR_PATH)


@db.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Aplica migraciones."""
    _alembic("upgrade", revision)


@db.command("downgrade")
def db_downgrade(revision: str = "-1") -> None:
    """Revierte migraciones."""
    _alembic("downgrade", revision)


@db.command("revision")
def db_revision(message: str = typer.Option(..., "-m", "--message")) -> None:
    """Genera una migración con autogenerate.

    SIEMPRE revisar el diff antes de aplicar: autogenerate propone, el humano decide.
    Si env.py no importa los modelos de TODOS los dominios, va a proponer borrar las
    tablas que no conoce.
    """
    _alembic("revision", "--autogenerate", "-m", message)
    typer.secho(
        "\n⚠  Revisá el archivo generado antes de aplicarlo.", fg=typer.colors.YELLOW
    )


@db.command("current")
def db_current() -> None:
    """Revisión aplicada actualmente."""
    _alembic("current")


@db.command("heads")
def db_heads() -> None:
    """Verifica que haya exactamente UN head.

    Es la mitigación del riesgo aceptado de la cadena única (ver 04-base-de-datos.md).
    Dos personas creando migraciones desde el mismo padre producen heads divergentes y
    `upgrade head` explota. Este check cuesta nada y elimina la clase entera de
    incidente — por eso está dentro de `oc check`.
    """
    out = subprocess.run(
        ["alembic", "heads"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ORCHESTRATOR_PATH,
    )
    heads = [ln for ln in out.stdout.splitlines() if ln.strip()]
    if len(heads) != 1:
        typer.secho(
            f"✗ Se esperaba 1 head de Alembic, hay {len(heads)}:", fg=typer.colors.RED
        )
        for h in heads:
            typer.echo(f"    {h}")
        typer.secho(
            "  Resolvelo con:  alembic merge -m 'merge heads' <rev1> <rev2>",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    typer.secho(f"✓ un solo head: {heads[0]}", fg=typer.colors.GREEN)

@app.command()
def lint(fix: bool = False) -> None:
    """ruff check (+ format con --fix)."""
    for d in DOMAINS:
        _run(["ruff", "check", *(["--fix"] if fix else []), "."], cwd=d.path)
        _run(["ruff", "format", *([] if fix else ["--check"]), "."], cwd=d.path)


# protoc emite el import del hermano en dos formas según el .proto:
#   proto plano                 →  import ejemplo_pb2
#   proto con package/carpetas  →  from todo.v1 import todo_pb2
# Las dos son absolutas y se rompen dentro de app/grpc_gen/. Hay que cubrir ambas.
_IMPORT_RE = re.compile(r"^import (\w+_pb2)", flags=re.MULTILINE)
_FROM_RE = re.compile(r"^from ([\w.]+) import (\w+_pb2)", flags=re.MULTILINE)


def _fix_generated_imports(out_dir: Path, root_pkg: str) -> None:
    """Reescribe los imports generados y crea los __init__.py.

    `root_pkg` es dónde vive el paquete visto desde el dominio ("app.grpc_gen").
    """
    # Los paquetes que salieron de ESTA generación. Es lo que distingue
    # `from todo.v1 import ...` (nuestro, hay que reescribir) de
    # `from google.protobuf import timestamp_pb2` (de la librería, no se toca).
    generados = {p.name for p in out_dir.iterdir() if p.is_dir()}

    def _absolutizar(m: re.Match) -> str:
        pkg, mod = m.group(1), m.group(2)
        if pkg.split(".")[0] not in generados:
            return m.group(0)
        return f"from {root_pkg}.{pkg} import {mod}"

    for py in out_dir.rglob("*_pb2*.py"):
        text = py.read_text(encoding="utf-8")
        fixed = _IMPORT_RE.sub(r"from . import \1", text)
        fixed = _FROM_RE.sub(_absolutizar, fixed)
        if fixed != text:
            py.write_text(fixed, encoding="utf-8")
    for pkg_dir in [out_dir, *[p for p in out_dir.rglob("*") if p.is_dir()]]:
        (pkg_dir / "__init__.py").touch(exist_ok=True)


@proto.command("gen")
def proto_gen(domain: str | None = None) -> None:
    """Genera los stubs Python (+ .pyi) desde los .proto."""
    for d in selected(domain):
        proto_dir = Path(d.path) / "proto"
        out_dir = Path(d.path) / "app" / "grpc_gen"
        out_dir.mkdir(parents=True, exist_ok=True)
        files = [str(p) for p in proto_dir.rglob("*.proto")]
        if not files:
            typer.secho(f"  {d.name}: sin .proto, salteando", fg=typer.colors.YELLOW)
            continue
        _run([
            sys.executable, "-m", "grpc_tools.protoc",
            f"--proto_path={proto_dir}",
            f"--python_out={out_dir}",
            f"--grpc_python_out={out_dir}",
            f"--pyi_out={out_dir}",
            *files,
        ])
        # "app/grpc_gen" -> "app.grpc_gen", derivado, no hardcodeado.
        root_pkg = ".".join(out_dir.relative_to(d.path).parts)
        _fix_generated_imports(out_dir, root_pkg)
        typer.secho(f"✓ {d.name}: stubs generados", fg=typer.colors.GREEN)


@proto.command("docs")
def proto_docs(out: str = "docs/proto") -> None:
    """Genera documentación navegable desde los comentarios de los .proto.

    Es el equivalente a Swagger UI. La otra mitad es reflection, que ya está encendida
    en los servidores y la consumen grpcurl, Postman y Apidog.
    """
    Path(out).mkdir(parents=True, exist_ok=True)
    for d in DOMAINS:
        proto_dir = Path(d.path) / "proto"
        files = [str(p) for p in proto_dir.rglob("*.proto")]
        if files:
            _run([
                "protoc", f"--proto_path={proto_dir}",
                f"--doc_out={out}", "--doc_opt=html,{}.html".format(d.name),
                *files,
            ])



@app.command()
def types() -> None:
    """Type checker."""
    for d in DOMAINS:
        _run([TYPE_CHECKER, "."], cwd=d.path)


@app.command()
def test(domain: str | None = None, cov: bool = False) -> None:
    """pytest en los dominios."""
    for d in selected(domain):
        cmd = ["pytest", "-q"]
        if cov:
            cmd += ["--cov=app", "--cov-report=term-missing"]
        _run(cmd, cwd=d.path)


@app.command()
def check() -> None:
    """Corre exactamente lo que corre CI. Si pasa acá, pasa allá."""
    lint(fix=False)
    types()
    test(domain=None, cov=False)
    db_heads()
    typer.secho("\n✓ todo en verde", fg=typer.colors.GREEN, bold=True)


if __name__ == "__main__":
    app()

