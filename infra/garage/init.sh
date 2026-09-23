#!/bin/sh
# infra/garage/init.sh — одноразовая инициализация Garage.
# Идемпотентен: повторный запуск не ломает существующие настройки.
#
# Что делает:
#   1. Ждёт, пока Garage RPC станет доступен.
#   2. Присваивает layout текущему узлу (capacity=1G — для dev достаточно).
#   3. Создаёт бакеты $S3_BUCKET_PHOTOS и $S3_BUCKET_AUDIT.
#   4. Импортирует ключ с access_key=$S3_ACCESS_KEY / secret=$S3_SECRET_KEY.
#   5. Даёт ключу права read/write на оба бакета.
#
# Использует ту же CLI-утилиту 'garage', что и сам сервер (образ dxflrs/garage).

set -eu

GARAGE_HOST="garage:3901"

echo "[garage-init] waiting for Garage RPC at ${GARAGE_HOST}..."
i=0
while ! garage -h "${GARAGE_HOST}" status >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 30 ]; then
    echo "[garage-init] FATAL: Garage RPC not reachable after 60s"
    exit 1
  fi
  sleep 2
done
echo "[garage-init] Garage RPC reachable."

# 1. Layout: находим ID узла и назначаем capacity (только если layout ещё не назначен).
NODE_ID=$(garage -h "${GARAGE_HOST}" node id 2>/dev/null | awk -F@ '{print $1}')
if [ -z "$NODE_ID" ]; then
  echo "[garage-init] FATAL: cannot determine node id"
  exit 1
fi

if ! garage -h "${GARAGE_HOST}" layout show 2>&1 | grep -q "$NODE_ID"; then
  echo "[garage-init] assigning layout to node ${NODE_ID}..."
  garage -h "${GARAGE_HOST}" layout assign -z dev -c 1G "$NODE_ID"
  garage -h "${GARAGE_HOST}" layout apply --version 1
  echo "[garage-init] layout applied."
else
  echo "[garage-init] layout already assigned, skipping."
fi

# 2. Bucket: photos
if ! garage -h "${GARAGE_HOST}" bucket list 2>/dev/null | grep -q "^ *${S3_BUCKET_PHOTOS} "; then
  echo "[garage-init] creating bucket ${S3_BUCKET_PHOTOS}..."
  garage -h "${GARAGE_HOST}" bucket create "${S3_BUCKET_PHOTOS}"
else
  echo "[garage-init] bucket ${S3_BUCKET_PHOTOS} exists, skipping."
fi

# 3. Bucket: audit
if ! garage -h "${GARAGE_HOST}" bucket list 2>/dev/null | grep -q "^ *${S3_BUCKET_AUDIT} "; then
  echo "[garage-init] creating bucket ${S3_BUCKET_AUDIT}..."
  garage -h "${GARAGE_HOST}" bucket create "${S3_BUCKET_AUDIT}"
else
  echo "[garage-init] bucket ${S3_BUCKET_AUDIT} exists, skipping."
fi

# 4. Key: импорт с фиксированными access_key/secret_key из .env.
if ! garage -h "${GARAGE_HOST}" key list 2>/dev/null | grep -q "${S3_ACCESS_KEY}"; then
  echo "[garage-init] importing key ${S3_ACCESS_KEY}..."
  garage -h "${GARAGE_HOST}" key import \
      --yes \
      --name course-bot-dev \
      "${S3_ACCESS_KEY}" "${S3_SECRET_KEY}"
else
  echo "[garage-init] key ${S3_ACCESS_KEY} already exists, skipping."
fi

# 5. Права ключа на бакеты (идемпотентно; повторное allow — no-op).
echo "[garage-init] granting key ${S3_ACCESS_KEY} R/W on buckets..."
garage -h "${GARAGE_HOST}" bucket allow \
    --read --write --owner \
    "${S3_BUCKET_PHOTOS}" --key "${S3_ACCESS_KEY}"
garage -h "${GARAGE_HOST}" bucket allow \
    --read --write --owner \
    "${S3_BUCKET_AUDIT}"  --key "${S3_ACCESS_KEY}"

echo "[garage-init] DONE. Buckets: ${S3_BUCKET_PHOTOS}, ${S3_BUCKET_AUDIT}. Ready."
