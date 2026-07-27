# 04 — Base de datos

> Una sola instancia de PostgreSQL, compartida por todos los dominios. Una única
> cadena de Alembic, ejecutada desde el CLI. Eso habilita transacciones que cruzan
> dominios, y a cambio exige disciplina en dos puntos: el presupuesto de conexiones y
> la propiedad de las tablas.

## Lo que la base compartida te da

- **Transacciones ACID que cruzan dominios.** Confirmar una recepción y mover stock en
  la misma transacción. Sin outbox, sin compensaciones, sin idempotencia manual.
- **Cero staleness.** No hay espejos ni caches que sincronizar; el dato es el dato.
- **JOINs entre dominios.** Las líneas de una OC con las variantes del catálogo en una
  sola query.
- **Un solo lugar donde mirar** cuando algo no cuadra.

## Lo que te cuesta

- **Los dominios no son independientes en el schema.** Un cambio de estructura se
  coordina; nadie migra en soledad.
- **Presupuesto de conexiones compartido.** Es el límite real de escalado, no el CPU.
- **Riesgo de heads divergentes** en la cadena única de Alembic. **Aceptado
  explícitamente** — ver los riesgos al final.

## El presupuesto de conexiones

Esto es lo más importante del documento, porque es donde el sistema se cae de verdad.

**En PostgreSQL cada conexión es un proceso del sistema operativo**, ~5–10 MB de RAM
en el servidor de base de datos, ocupada esté o no en uso. `pool_size` son conexiones
**permanentes**: nunca se cierran. `max_overflow` son de pico: se abren cuando hace
falta y se cierran al devolverlas.

### La invariante

```
conexiones_permanentes  =  Σ (dominios × DB_POOL_SIZE)
techo_de_pico           =  Σ (dominios × (DB_POOL_SIZE + DB_MAX_OVERFLOW))

y por dominio:   GRPC_MAX_WORKERS  <=  DB_POOL_SIZE + DB_MAX_OVERFLOW
```

La segunda parte es porque cada hilo del pool de gRPC que consulta la base ocupa una
conexión. Si hay más hilos que conexiones, los hilos de más se quedan esperando
`pool_timeout` segundos y el worker se congela sin razón aparente.

### Números de arranque

Por dominio:

```
GRPC_MAX_WORKERS = 10
DB_POOL_SIZE     = 3        # PERMANENTES
DB_MAX_OVERFLOW  = 7        # de pico, baratas
DB_POOL_TIMEOUT  = 10       # fallar rápido; esperar 30 s congela el worker
DB_POOL_RECYCLE  = 1800     # RDS corta conexiones ociosas
DB_POOL_PRE_PING = true
```

Con 5 dominios: **15 conexiones permanentes**, techo de pico **50**.

### Por qué esos números y no los de siempre

El CRM actual documenta un incidente real: `pool_size=20 × 2 workers = 40 conexiones
permanentes` contra una instancia de **1 GB** dejó la base sin RAM, entró en swap, y
la latencia se multiplicó por 50.

Con 5 dominios a `pool_size=5` (el default habitual) serían 25 permanentes y 100 de
pico — territorio del mismo incidente. De ahí el `pool_size=3`: los dominios sirven
pocas personas y no necesitan conexiones permanentes reservadas; la holgura la da el
overflow, que se devuelve.

> **Pendiente:** la clase de instancia actual. Sin ese dato los números de arriba son
> conservadores por precaución, no calculados. Antes de cualquier prueba de carga hay
> que confirmarlo y recalcular.

### PgBouncer no es el atajo

La respuesta habitual a "muchos procesos, una Postgres" es PgBouncer en modo
transacción. Acá **rompe algo**: el scheduler del CRM usa `pg_try_advisory_lock`, que
es un lock **de sesión**, y el pooling en modo transacción lo invalida. Si algún
dominio necesita elegir un líder entre réplicas, PgBouncer en modo transacción se lo
lleva puesto. Si se evalúa, va con esa restricción sobre la mesa.

## Cambiar de motor: Postgres o SQLite

Se cambia con **una sola línea** del `.env`, igual que en el CRM actual:

```bash
DATABASE_URL=postgresql://dev:dev@localhost:5432/plataforma   # producción y dev con docker
DATABASE_URL=sqlite:///./dominio.db                            # dev local sin docker
DATABASE_URL=sqlite:///:memory:                                # tests
```

La bifurcación vive en `app/db/session.py` y **no es cosmética**: SQLite no acepta
`pool_size` ni `max_overflow` — su pool por defecto es `SingletonThreadPool` o
`NullPool`, y pasarle esos argumentos lanza `TypeError` al crear el engine.

| | Postgres | SQLite |
|---|---|---|
| Pool | `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`, `pre_ping` | ninguno |
| `connect_args` | — | `check_same_thread: False` |
| Pool en memoria | — | **`StaticPool`** |

Los dos casos de `connect_args` y `StaticPool` merecen la explicación porque los
síntomas no señalan la causa:

- **`check_same_thread: False`** — el servidor gRPC atiende cada RPC en un hilo del
  pool, y SQLite por defecto prohíbe usar una conexión desde otro hilo del que la
  creó.
- **`StaticPool` con `:memory:`** — sin él, **cada conexión abre una base en memoria
  distinta y vacía**. Las tablas que creó el fixture no existen para el resto del test,
  y el error que sale es `no such table`, que no dice nada del pool.

### SQLite queda prohibido fuera de dev y test

`config.py` **aborta el arranque** si `DATABASE_URL` apunta a SQLite y `APP_ENV` no es
`development` ni `test`.

La razón: la comodidad de "cambio una línea del `.env`" es exactamente el mecanismo por
el que un typo llega a producción. Mejor que no arranque que servir tráfico sobre un
archivo.

### Qué NO va a funcionar en SQLite

| Feature | Qué hacer |
|---|---|
| **JSONB + índices GIN** | `JSON().with_variant(JSONB(), "postgresql")`, y el índice GIN condicional solo en Postgres |
| **Advisory locks** (`pg_try_advisory_lock`) | No existen. Si un dominio elige líder entre réplicas para correr jobs, ese camino **no se puede testear en SQLite** |
| **`ON CONFLICT`** | El upsert difiere |
| **`ALTER TABLE`** | Muy limitado: renombrar o cambiar tipos necesita `batch_alter_table` de Alembic |
| **Índices parciales** | Soportados, con sintaxis y cobertura distintas |

**Consecuencia práctica: un test que pasa en SQLite puede fallar en Postgres.** La
verdad de las migraciones se valida contra Postgres, no contra SQLite.

Y con base compartida: SQLite tiene un **write-lock global por archivo**, así que
varios dominios escribiendo el mismo `.db` se serializan entre sí. Anda para un dev y
para tests; no refleja el comportamiento real bajo concurrencia.

## Migraciones: cadena única desde el CLI

Una sola cadena de Alembic. Vive en el orquestador, no en los dominios.

```
orquestador/
├── cli.py
└── alembic/
    ├── env.py              # importa los modelos de TODOS los dominios
    ├── script.py.mako
    └── versions/           # una sola cadena lineal
```

```bash
oc db upgrade          # alembic upgrade head
oc db revision -m "..." # autogenerate
oc db heads            # tiene que devolver exactamente 1
```

### Por qué global y no por dominio

Porque con base compartida y FKs entre dominios hace falta **orden determinista**: si
las líneas de OC referencian `shop_product_variants`, esa tabla tiene que existir
antes. Una cadena única resuelve el orden por construcción.

### El precio, y la mitigación obligatoria

Una cadena + varios autores = **heads divergentes**. Dos personas crean una migración
desde el mismo padre, y `alembic upgrade head` explota con "Multiple heads". En el CRM
actual eso dejó producción con schema roto sirviendo 500 en dos ocasiones.

**Mitigación, no opcional:** un test en CI que falle si hay más de un head.

```python
def test_single_alembic_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    heads = script.get_heads()
    assert len(heads) == 1, f"Múltiples heads de Alembic: {heads}"
```

Cuesta diez líneas y elimina la clase entera de incidente. **Va en CI desde el primer
día.**

### `autogenerate` y el pie de plomo

`env.py` tiene que importar los modelos de **todos** los dominios. Si importa solo los
de uno, `autogenerate` va a ver el resto de las tablas como "sobrantes" y va a emitir
`op.drop_table()` para cada una.

```python
# alembic/env.py
from shared.db.base import Base
from dominios.compras.app.db import models as compras_models   # noqa: F401
from dominios.otro.app.db import models as otro_models         # noqa: F401

target_metadata = Base.metadata
```

Y **leer siempre el diff generado antes de aplicarlo.** `autogenerate` propone; el
humano decide.

### Migraciones no destructivas

Solo `ADD COLUMN` y `CREATE TABLE` en el curso normal. Renombrar o eliminar exige
aprobación explícita y backup previo. Cuando un cambio de schema tiene que cruzar un
deploy sin coordinar, el patrón es **expand/contract**: agregar lo nuevo, migrar los
datos, dejar de usar lo viejo, y solo después quitarlo — en tres despliegues, no en
uno.

## Propiedad de las tablas

Esta es la disciplina que decide si la base compartida se mantiene sana o se podre.

### La regla

**Cada tabla tiene un dominio dueño. Solo él la escribe. Los demás la leen.**

Y no es sobre concurrencia — dos escrituras simultáneas las resuelve PostgreSQL con
MVCC y locks de fila. Es sobre **quién tiene derecho a cambiar el significado** de una
tabla a lo largo del tiempo. El daño de romper esto no aparece el día que lo hacés:
aparece meses después, lejos, y en silencio.

### Los límites se dibujan donde las transacciones no cruzan

Un ejemplo concreto: **el ingreso de mercadería pertenece a compras.** Una orden de
compra *es* la entrada de productos al inventario; que compras escriba stock al
confirmar una recepción no es violar un límite, es su trabajo. Si se pusiera "stock"
como un dominio separado, se estaría dibujando la línea por el medio de una
transacción — y todo el dolor posterior saldría de ahí.

La regla práctica: **si dos cosas tienen que pasar o no pasar juntas, están en el
mismo dominio.**

### Cuando un dominio lee tablas de otro

Va por **un solo repositorio** que sea el único lugar del dominio que conoce el nombre
de la tabla ajena. Si mañana el dueño renombra una columna, se toca un archivo y no
veinte. Es un Anti-Corruption Layer, y su valor es concentrar el acoplamiento en un
punto visible.

```python
# app/repositories/catalog_reader.py
# ÚNICO lugar de este dominio que conoce el schema del catálogo.
# Solo lectura. Si el dueño cambia algo, se arregla acá.
class CatalogReader:
    def find_variant(self, variant_id: int) -> VariantSnapshot | None:
        ...
```

Y donde se pueda, reforzarlo a nivel base con `GRANT SELECT` sobre las tablas ajenas,
para que escribir donde no corresponde sea **imposible**, no solo mal visto.

### Y si un dominio necesita ejecutar una regla de otro

Escribir una tabla ajena correctamente a veces exige conocer reglas que no están en el
schema — un state machine, un movimiento que se registra en pares, un flag que se
levanta en cierto caso. Reimplementarlas en el dominio lector es garantía de
divergencia silenciosa.

La salida sana: **la regla vive en una librería compartida** y el dominio lector la
importa y la ejecuta contra la base, dentro de su propia transacción. La regla existe
una sola vez, la transacción se preserva, y el acoplamiento queda a nivel de
dependencia — visible en el `pyproject.toml`, no escondido en un `UPDATE`.

## Registro de dueños

Tabla que hay que mantener a medida que aparecen dominios. Es el artefacto que hace
cumplible todo lo de arriba.

| Tabla | Dominio dueño | Quién lee |
|---|---|---|
| `suppliers` | compras | — |
| `supplier_products` | compras | — |
| `purchase_orders` | compras | — |
| `purchase_order_lines` | compras | — |
| `purchase_order_change_log` | compras | — |
| `receptions`, `reception_lines` | compras | — |
| *(a completar)* | | |

## Riesgos aceptados

| Riesgo | Estado | Mitigación |
|---|---|---|
| Heads divergentes en la cadena única | **Aceptado explícitamente** | test de un solo head en CI |
| Si cae la base, cae todo | **Inherente** a una sola instancia | backups, y la decisión de no separar |
| Acoplamiento de schema entre dominios | Aceptado a cambio del ACID | repositorio único por tabla ajena + `GRANT SELECT` |
| `autogenerate` borrando tablas ajenas | Evitable | `env.py` importa todos los modelos + leer el diff |

## Pendientes

- **Clase de la instancia** — necesaria para recalcular el presupuesto de conexiones.
- **¿Schema propio por dominio (`compras.*`) o todo en `public`?** Con cadena global lo
  natural es `public`; un schema por dominio agrega claridad de propiedad a costa de
  `search_path` en cada sesión.
- **¿Se usan FKs entre dominios?** Con cadena global son seguras. Ponerlas da
  integridad referencial; no ponerlas deja los dominios más despegados.
- **Namespacear los advisory locks** por dominio, si más de uno corre jobs
  programados. Con la misma clave se bloquean entre sí.
