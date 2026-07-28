ARG PYTHON_VERSION=3.14

FROM python:${PYTHON_VERSION}-slim AS builder

ARG DOMAIN_PATH
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv


COPY ${DOMAIN_PATH}/pyproject.toml ./
RUN uv venv /venv && VIRTUAL_ENV=/venv uv pip install -r pyproject.toml --all-extras

# Los stubs ya vienen en app/grpc_gen: los genera `oc proto gen` antes del build.
COPY ${DOMAIN_PATH}/proto ./proto
COPY ${DOMAIN_PATH}/app ./app


FROM python:${PYTHON_VERSION}-slim AS runtime

ARG DOMAIN_PATH
WORKDIR /code


RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*


ARG GRPC_HEALTH_PROBE_VERSION=v0.4.53
ADD https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 /bin/grpc_health_probe
RUN chmod +x /bin/grpc_health_probe


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/venv/bin:$PATH"


COPY --from=builder /venv /venv
COPY --from=builder /build/app ./app
COPY ${DOMAIN_PATH}/proto ./proto
COPY ${DOMAIN_PATH}/.env ./.env
# Dev: la base viaja con la imagen. Lo que se escriba dentro muere con el contenedor.
COPY ${DOMAIN_PATH}/todo.db ./todo.db

EXPOSE 50051


HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD /bin/grpc_health_probe -addr=:50051 || exit 1

CMD ["python", "-m", "app.server"]

