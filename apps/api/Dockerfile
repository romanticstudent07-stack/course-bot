# apps/api/Dockerfile — FastAPI backend
# Правило IRONCLAD: python:3.12-slim (архитектура требует Py 3.12), не хост-Python 3.14.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # `alembic upgrade head` работает из любого каталога контейнера
    # (infra/README.md: `docker compose ... exec api alembic upgrade head`).
    ALEMBIC_CONFIG=/app/migrations/alembic.ini

WORKDIR /app

# Системные зависимости (минимум) — curl для HEALTHCHECK.
# psycopg[binary] несёт libpq в wheel — build-essential/libpq-dev не нужны.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Python-зависимости отдельным слоем — быстрая пересборка при правке кода.
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# Код. .dockerignore рядом не пускает в образ .env, .git, __pycache__, tests/.
COPY . /app/

# Непривилегированный пользователь.
RUN useradd --system --uid 10001 --no-create-home app && chown -R app /app
USER app

# Health endpoint должен ответить 200 на /healthz.
# Порт — тот же, что в CMD (внутренний порт контейнера), а не APP_PORT:
# при APP_PORT≠8080 проверка иначе стучалась бы не туда (см. «Вопросы Автору» в PR).
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

EXPOSE 8080

# Порт 8080 внутри контейнера совпадает с APP_PORT по умолчанию (.env.example).
# Публикация на хосте — только 127.0.0.1 (infra/docker-compose.dev.yml).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
