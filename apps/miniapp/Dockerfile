# apps/miniapp/Dockerfile — React + Vite + TypeScript
# Правило IRONCLAD: Node на хосте не установлен, сборка ТОЛЬКО в Docker.
# Multi-stage: builder (node:20-alpine) → runtime (nginx:alpine со статикой).

# --- Stage 1: builder ---
FROM node:20-alpine AS builder
WORKDIR /app

# Зависимости отдельным слоем.
# Паттерн 'package.json* package-lock.json*' безопасен даже если файлов пока нет:
# glob с буквальным префиксом в Docker BuildKit не падает при пустом совпадении.
COPY package.json* package-lock.json* pnpm-lock.yaml* yarn.lock* ./
RUN if [ -f package.json ]; then \
        if [ -f package-lock.json ]; then npm ci; \
        else npm install; \
        fi \
    ; fi

# Исходники → сборка.
# .dockerignore рядом защищает от .env, .git, node_modules, dist.
COPY . .
RUN if [ -f package.json ] && grep -q '"build"' package.json; then npm run build; \
    else \
        mkdir -p /app/dist && \
        echo '<!doctype html><html><body><h1>Mini App stub — Iteration 0-A pending</h1></body></html>' > /app/dist/index.html; \
    fi

# --- Stage 2: runtime ---
FROM nginx:alpine

# CSP-заголовок из E2 ERRATA: default-src 'self' + whitelist, unsafe-eval запрещён.
# Полный конфиг nginx с CSP Агент положит в apps/miniapp/nginx.conf позже.
COPY --from=builder /app/dist /usr/share/nginx/html

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD wget -q -O - http://127.0.0.1/ >/dev/null || exit 1

EXPOSE 80
