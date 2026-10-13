FROM python:3.14-slim

WORKDIR /invoicer-api

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Compile dependencies once at build time; the app can't write bytecode itself
ENV UV_COMPILE_BYTECODE=1 PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/invoicer-api/.venv/bin:$PATH"

# Run as www-data (uid 33). The code stays owned by root, so the app can't
# change it; only the folders it writes to belong to www-data. When these are
# mounted from the host, the host folders must be owned by uid 33 too.
RUN mkdir -p uploads logs && chown www-data:www-data uploads logs
USER www-data

EXPOSE 5000

CMD ["/invoicer-api/boot.sh"]
