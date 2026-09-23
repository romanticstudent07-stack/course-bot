# apps/miniapp/Dockerfile — React + Vite + TypeScript
# Правило IRONCLAD: Node на хосте не установлен, сборка ТОЛЬКО в Docker.
# Multi-stage: builder (node:20-alpine) → runtime (nginx:alpine со статикой).

# --- Stage 1: builder ---
FROM node:20-alpine AS builder
WORKDIR /app

# Зависимости отдельным слоем — пересборка кода не переустанавливает node_modules.
# package-lock.json закоммичен → воспроизводимая установка через npm ci.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Исходники → сборка (tsc --noEmit && vite build → /app/dist).
# .dockerignore рядом защищает от .env, .git, node_modules, dist.
# VITE_API_BASE_URL — build-time переменная (пусто = тот же origin, CSP E2 connect-src 'self').
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
COPY . .
RUN npm run build

# --- Stage 2: runtime ---
FROM nginx:alpine

# CSP-заголовок из E2 ERRATA задаётся в nginx.conf (default-src 'self',
# unsafe-eval запрещён, frame-ancestors ограничен Telegram).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD wget -q -O - http://127.0.0.1/healthz >/dev/null || exit 1

EXPOSE 80
