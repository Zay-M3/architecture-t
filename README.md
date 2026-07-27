# Plantillas

Esqueletos para copiar. Son **mínimos y ejecutables**: el objetivo es que `oc up` y
`oc check` pasen en verde con cero lógica de negocio. La lógica se escribe después,
encima.

```
plantillas/
├── dominio/          → un dominio gRPC completo (copiar por cada dominio nuevo)
├── transformador/    → Astro SSR + cliente gRPC + SSE
├── orquestador/      → el CLI Typer + la cadena de Alembic
└── docker/           → Dockerfiles y compose
```

## Cómo arrancar

```bash
# 1. copiar la estructura
cp -r plantillas/dominio        ../../dominios/compras
cp -r plantillas/transformador  ../../transformador
cp -r plantillas/orquestador    ../../orquestador
cp plantillas/docker/*          ../../

# 2. registrar el dominio en orquestador/config.py

# 3. instalar
oc install

# 4. generar stubs
oc proto gen

# 5. levantar
oc up

# 6. verificar que el andamio está sano
oc check
```

**El hito cero es que el paso 6 pase en verde con el dominio vacío.** Si el andamio no
está sano antes de escribir negocio, cada bug después va a ser ambiguo entre "mi lógica"
y "la infraestructura".

## Lo que estas plantillas NO traen

- Auth — va en un servicio aparte.
- Lógica de Órdenes de Compra — se diseña sobre esto.
- Migraciones con tablas reales — solo la cadena vacía.
- Dragonfly — pendiente de definir su rol (ver `07-decisiones-y-pendientes.md`, P3).
