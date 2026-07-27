# 06 — El orquestador

> Un CLI en Typer. Es la interfaz humana de la plataforma: levanta contenedores, corre
> migraciones, ejecuta tests, pasa ruff y el type checker, genera stubs.

## Qué es y qué no es

| Es | No es |
|---|---|
| La forma de operar la plataforma con un comando | Un gestor de procesos |
| El dueño de la cadena de Alembic | Un supervisor que reinicia lo que se cae |
| El que sabe en qué orden se levanta todo | Parte del camino de ningún request |

**Docker levanta y supervisa.** Typer solo da los comandos. La distinción importa: si
Typer fuera el process manager habría que resolver reinicio automático, health checks y
rolling restarts, que es exactamente el trabajo que Docker ya hace.

## Estructura

```
orquestador/
├── pyproject.toml
├── cli.py                  # los comandos
├── config.py               # registro de dominios: nombre, puerto, carpeta
├── alembic.ini
└── alembic/
    ├── env.py              # importa los modelos de TODOS los dominios
    ├── script.py.mako
    └── versions/           # cadena única
```

El registro de dominios es una sola estructura y de ahí sale todo lo demás:

```python
# config.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Domain:
    name: str
    path: str
    grpc_port: int

DOMAINS = (
    Domain(name="compras", path="dominios/compras", grpc_port=50051),
)

TRANSFORMER_PATH = "transformador"
```

Agregar un dominio = una línea acá. Los comandos lo recogen solos.

## Comandos

```
oc up [--domain X]              levanta todo (o un dominio) con docker compose
oc down                         baja todo
oc logs [--domain X] [-f]       logs
oc ps                           estado de los contenedores

oc db upgrade                   alembic upgrade head
oc db revision -m "..."         autogenerate — SIEMPRE revisar el diff
oc db downgrade -1              rollback de una revisión
oc db heads                     tiene que devolver exactamente 1
oc db current                   revisión aplicada

oc proto gen [--domain X]       genera stubs Python + .pyi, parchea imports
oc proto lint                   valida convenciones del .proto
oc proto docs                   protoc-gen-doc → HTML/Markdown

oc test [--domain X] [--cov]    pytest
oc lint [--fix]                 ruff check (+ format con --fix)
oc types                        type checker
oc check                        lint + types + test — lo que corre CI

oc dev [--domain X]             watchfiles + servidor gRPC, con recarga
oc shell --domain X             REPL con el container del dominio cargado
```

### `oc check` es el gate

Un solo comando que corre lo mismo que CI, en el mismo orden. Si pasa en local, pasa en
CI.

```python
@app.command()
def check() -> None:
    """Corre lo mismo que CI: formato, tipos, tests."""
    _run(["ruff", "check", "."])
    _run(["ruff", "format", "--check", "."])
    _run([TYPE_CHECKER, "."])
    _run(["pytest", "-q"])
    _alembic("heads", expect_single=True)
```

El `heads` va acá adentro a propósito: es la mitigación del riesgo aceptado de la
cadena única de Alembic ([`04-base-de-datos.md`](04-base-de-datos.md)), y si no está en
el gate no sirve de nada.

## Generación de stubs

El comando `proto gen` resuelve el gotcha conocido de `grpc_tools.protoc`: los imports
que emite son absolutos y se rompen dentro de un paquete.

```python
@app.command("gen")
def proto_gen(domain: str | None = None) -> None:
    for d in _selected(domain):
        out = Path(d.path) / "app" / "grpc_gen"
        out.mkdir(parents=True, exist_ok=True)
        _run([
            "python", "-m", "grpc_tools.protoc",
            f"--proto_path={d.path}/proto",
            f"--python_out={out}",
            f"--grpc_python_out={out}",
            f"--pyi_out={out}",
            *[str(p) for p in Path(f"{d.path}/proto").rglob("*.proto")],
        ])
        _fix_generated_imports(out)   # absolutos → relativos
        _touch_init_files(out)
```

`app/grpc_gen/` no se commitea. Se regenera con este comando y en el build de la imagen.

## Desarrollo con recarga

gRPC no trae `--reload`. Se envuelve con `watchfiles`, que es lo que uvicorn usa por
dentro:

```python
@app.command()
def dev(domain: str) -> None:
    """Levanta un dominio con recarga al guardar."""
    d = _domain(domain)
    _run(["watchfiles", "python -m app.server", "app/"], cwd=d.path)
```

## Entornos con uv

Cada dominio tiene su propio `pyproject.toml` y su propio entorno. El CLI no comparte
dependencias entre dominios — eso es parte de que sean independientes.

```bash
oc install              # uv sync en cada dominio + el transformador
oc install --domain compras
```

```python
@app.command()
def install(domain: str | None = None) -> None:
    for d in _selected(domain):
        _run(["uv", "sync", "--all-groups"], cwd=d.path)
    if domain is None:
        _run(["bun", "install"], cwd=TRANSFORMER_PATH)
```

## Sobre el type checker

Está pendiente elegir cuál. Si es **`ty`** (de Astral, los mismos de ruff y uv), tener
presente que es muy nuevo y pre-1.0: conviene correrlo junto a mypy o pyright un tiempo
antes de dejarlo como único gate. Si es mypy o pyright, no hay nada que aclarar.

El CLI lo toma de una constante para que cambiarlo sea una línea:

```python
TYPE_CHECKER = "ty"   # o "mypy" / "pyright"
```

## Por qué Typer

Es de la misma gente que FastAPI, deriva la interfaz de los type hints, y produce
`--help` decente sin trabajo extra. Para un CLI interno que va a crecer con comandos es
la elección obvia — y acá se usa exactamente para lo que es: una interfaz de línea de
comandos, no un runtime.
