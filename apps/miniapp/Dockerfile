# apps/miniapp/Dockerfile — React + Vite + TypeScript
# Правило IRONCLAD: Node на хосте не установлен, сборка ТОЛЬКО в Docker.
# Multi-stage: builder (node:20-alpine) → runtime (nginx:alpine со статикой).

# --- Stage 1: builder ---
FROM node:20-alpine AS builder
WORKDIR /app

# Зависимости отдельным слоем.
COPY package*.json ./
RUN if [ -f package.json ]; then npm ci; fi

# Исходники → сборка.
COPY . .
RUN if [ -f package.json ]; then npm run build; fi

# --- Stage 2: runtime ---
FROM nginx:alpine

# CSP-заголовок из E2 ERRATA: default-src 'self' + whitelist, unsafe-eval запрещён.
# Полный конфиг nginx с CSP Агент положит в apps/miniapp/nginx.conf позже.
COPY --from=builder /app/dist /usr/share/nginx/html

# Заглушка index.html — если Итерация 0-А ещё не завершена.
RUN if [ ! -f /usr/share/nginx/html/index.html ]; then \
        echo '<!doctype html><html><body><h1>Mini App stub — Iteration 0-A pending</h1></body></html>' \
            > /usr/share/nginx/html/index.html; \
    fi

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD wget -q -O - http://127.0.0.1/ >/dev/null || exit 1

EXPOSE 80
