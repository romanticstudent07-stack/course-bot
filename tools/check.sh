#!/usr/bin/env bash
# tools/check.sh — быстрые проверки в Codespaces (без БД и без Docker).
# Тесты с БД, сборку Docker-образов и guard делает CI в PR.
#
# Запуск (из любой папки репо):
#   bash tools/check.sh              # eol + exec + api + bot + miniapp
#   bash tools/check.sh api          # eol + exec + только нужное: api / bot / miniapp (можно несколько)
# Лог: .tmp/check.log  →  в чат КОДЕР:  tail -n 60 .tmp/check.log

set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2
mkdir -p .tmp
LOG=.tmp/check.log
: > "$LOG"

targets=("$@")
[ ${#targets[@]} -eq 0 ] && targets=(api bot miniapp)

py_app() {  # $1 = api | bot; у каждого своё окружение apps/<app>/.venv (в .gitignore)
  cd "apps/$1" || return 1
  [ -x .venv/bin/python ] || python3 -m venv .venv || return 1
  .venv/bin/pip install -q --disable-pip-version-check -r requirements-dev.txt || return 1
  # Фиктивные значения, как в ci.yml. DATABASE_URL не задан → тесты с БД пропускаются (их гоняет CI).
  BOT_TOKEN=ci-fake-bot-token WEBHOOK_SECRET=ci-fake-webhook-secret .venv/bin/python -m pytest -q
}

miniapp_app() {
  cd apps/miniapp || return 1
  if [ ! -d node_modules ] || [ package-lock.json -nt node_modules/.package-lock.json ]; then
    npm ci --no-audit --no-fund || return 1
  fi
  npx tsc --noEmit && npx vitest run
}

fail=0

# 0. Концы строк: в git только LF (github.dev / vscode.dev игнорируют .gitattributes и пишут CRLF).
echo "===== eol =====" | tee -a "$LOG"
bad_eol=$(git ls-files --eol | grep -E '^i/(crlf|mixed)' || true)
if [ -n "$bad_eol" ]; then
  echo "$bad_eol" | tee -a "$LOG"
  echo "[УПАЛО] eol — почини: git add --renormalize . && git commit -m 'chore: LF'" | tee -a "$LOG"
  fail=1
else
  echo "[OK] eol" | tee -a "$LOG"
fi

# 0б. Право на запуск: каждый *.sh (в git и новый) должен быть исполняемым.
#     github.dev и tools/unpack.py создают файлы без +x; git хранит это право (режим 100755).
echo "===== exec =====" | tee -a "$LOG"
bad_x=""
while IFS= read -r f; do
  if [ -e "$f" ] && [ ! -x "$f" ]; then bad_x="$bad_x $f"; fi
done < <(git ls-files -co --exclude-standard -- '*.sh')
if [ -n "$bad_x" ]; then
  echo "Нет права на запуск:$bad_x" | tee -a "$LOG"
  echo "[УПАЛО] exec — почини: chmod +x$bad_x  (потом снова bash tools/check.sh)" | tee -a "$LOG"
  fail=1
else
  echo "[OK] exec" | tee -a "$LOG"
fi

for t in "${targets[@]}"; do
  echo "===== $t =====" | tee -a "$LOG"
  case "$t" in
    api|bot) ( py_app "$t" ) 2>&1 | tee -a "$LOG"; rc=${PIPESTATUS[0]} ;;
    miniapp) ( miniapp_app ) 2>&1 | tee -a "$LOG"; rc=${PIPESTATUS[0]} ;;
    *) echo "Неизвестная цель: $t (можно: api bot miniapp)"; exit 2 ;;
  esac
  if [ "$rc" -ne 0 ]; then
    echo "[УПАЛО] $t" | tee -a "$LOG"; fail=1
  else
    echo "[OK] $t" | tee -a "$LOG"
  fi
done

echo
if [ "$fail" -eq 0 ]; then
  echo "ИТОГ: всё зелёное. Можно коммитить."
else
  echo "ИТОГ: есть падения. Отправь в чат КОДЕР вывод команды: tail -n 60 .tmp/check.log"
fi
exit "$fail"
