# apps/bot/Dockerfile — Telegram Bot (aiogram 3, Python 3.12)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt* /app/
RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

COPY . /app/

# Итерация 0-А: заглушка бота — просто спит, чтобы контейнер не падал.
# Агент заменит на реальный aiogram 3 dispatcher.
CMD ["python", "-c", "import time, os; print('bot stub is idle; waiting for Iteration 0-A code'); \nwhile True: time.sleep(3600)"]
