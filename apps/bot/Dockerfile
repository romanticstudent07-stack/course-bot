# apps/bot/Dockerfile — Telegram Bot (aiogram 3, Python 3.12)
# Правило IRONCLAD: python:3.12-slim, не хост-Python.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Зависимости отдельным слоем — быстрая пересборка при правке кода.
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# Код. .dockerignore рядом не пускает в образ .env, .git, __pycache__, tests/.
COPY . /app/

# Непривилегированный пользователь.
RUN useradd --system --uid 10001 --no-create-home app && chown -R app /app
USER app

# Long polling: входящих портов нет, EXPOSE не нужен (правило IRONCLAD).
# BOT_TOKEN, WEBAPP_URL — из .env (compose: env_file ../.env).
CMD ["python", "-m", "bot"]
