"""CLI de la plataforma.

Typer es la INTERFAZ. Docker levanta y supervisa los procesos; Alembic migra. Este
archivo no es un gestor de procesos: si lo fuera, habría que resolver reinicio
automático, health checks y rolling restart, que es exactamente lo que Docker ya hace.

Uso:  oc --help
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import typer

from config import DOMAINS, TRANSFORMER_PATH, TYPE_CHECKER, domain_by_name, selected

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


# ── Ciclo de vida ────────────────────────────────────────────────────────────
@app.command()
def up(domain: str | None = None, build: bool = False) -> None:
    """Levanta la plataforma (o un dominio) con docker compose."""
    cmd = ["docker", "compose", "up", "-d"]
    if build:
        cmd.append("--build")
    if domain:
        cmd.append(domain_by_name(domain).name)
    _run(cmd)


@app.command()
def down() -> None:
    """Baja la plataforma."""
    _run(["docker", "compose", "down"])


@app.command()
def logs(domain: str | None = None, follow: bool = True) -> None:
    """Logs de la plataforma o de un dominio."""
    cmd = ["docker", "compose", "logs"]
    if follow:
        cmd.append("-f")
    if domain:
        cmd.append(domain_by_name(domain).name)
    _run(cmd)


@app.command()
def ps() -> None:
    """Estado de los contenedores."""
    _run(["docker", "compose", "ps"])


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


# ── Migraciones ──────────────────────────────────────────────────────────────
def _alembic(*args: str) -> None:
    _run(["alembic", *args])


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
        ["alembic", "heads"], capture_output=True, text=True, check=False
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


# ── Contratos gRPC ───────────────────────────────────────────────────────────
_IMPORT_RE = re.compile(r"^import (\w+_pb2)", flags=re.MULTILINE)


def _fix_generated_imports(out_dir: Path) -> None:
    """grpc_tools.protoc emite `import xxx_pb2` con rutas absolutas que se rompen dentro
    de un paquete. Se pasan a relativas y se crean los __init__.py."""
    for py in out_dir.rglob("*_pb2*.py"):
        text = py.read_text(encoding="utf-8")
        fixed = _IMPORT_RE.sub(r"from . import \1", text)
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
        _fix_generated_imports(out_dir)
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


# ── Calidad ──────────────────────────────────────────────────────────────────
@app.command()
def lint(fix: bool = False) -> None:
    """ruff check (+ format con --fix)."""
    for d in DOMAINS:
        _run(["ruff", "check", *(["--fix"] if fix else []), "."], cwd=d.path)
        _run(["ruff", "format", *([] if fix else ["--check"]), "."], cwd=d.path)


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
