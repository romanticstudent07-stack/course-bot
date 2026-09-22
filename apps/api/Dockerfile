# apps/api/Dockerfile — FastAPI backend
# Правило IRONCLAD: python:3.12-slim (архитектура требует Py 3.12), не хост-Python 3.14.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Системные зависимости (минимум) — psycopg, healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Python-зависимости отдельным слоем — быстрая пересборка при правке кода.
# Обе строки безопасны при отсутствии файла (glob с буквальным префиксом не падает).
COPY requirements.txt* /app/
COPY pyproject.toml* poetry.lock* /app/
RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

# Код (Агент положит его в apps/api/ при Итерации 0-А).
# .dockerignore рядом обеспечивает, чтобы сюда не попали .env, .git, __pycache__.
COPY . /app/

# Health endpoint должен ответить 200 на /healthz.
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD curl -fsS http://127.0.0.1:${APP_PORT:-8080}/healthz || exit 1

EXPOSE 8080

# Итерация 0-А: stub.py слушает /healthz. Агент заменит на:
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
CMD ["python", "stub.py"]
