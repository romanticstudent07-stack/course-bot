# miniapp-csp — CSP: font-src без data: (D-20 = А) + favicon.ico 204 + nosniff на статике

## 1. Паспорт
- id: miniapp-csp · PR: «miniapp-csp: font-src без data: (D-20), favicon 204, nosniff статики» · ветка: feat/miniapp-csp
- Режим: Р0+ (область miniapp) · зависит от: projector-3 (очередь). Миграции нет. Начинать после мержа projector-3.
- Первый файл пакета — docs/STATE.md (строки от ШТАБа).

## 2. Цель
CSP перестаёт быть шире E2 в font-src; комментарий говорит правду. /favicon.ico перестаёт давать 404 на каждое открытие.
Статика (.js, .css и др.) получает X-Content-Type-Options: nosniff, который сейчас теряется из-за своего add_header.

## 3. Решения Автора (дословно)
- D-20 (04.10): «А: убрать data: из font-src в apps/miniapp/nginx.conf и поправить комментарий; сервер 04.10
  проверил сборку — шрифтов нет (ни data:, ни файлов); появятся шрифты — font-src правится в той же задаче».
- STATE, Мелочи: «miniapp nginx: 404 favicon.ico на каждое открытие — безвредно, добавить при ближайшей правке сборки miniapp.»
- ШТАБ (04.10): favicon — решение ПРОЕКТИРОВЩИКА, без внешних запросов, CSP не ослаблять.
- ШТАБ (05.10): «взять находку nosniff. В location статики (~* \.(js|css|…)$) добавить строку
  add_header X-Content-Type-Options "nosniff" always; — рядом с его Cache-Control; CSP туда НЕ добавлять (действует на документ).»

## 4. Выдержки (a4c5e29)
- E2 csp_final (errata-unified): директивы font-src нет — для шрифтов действует default-src 'self'.
- nginx.conf, комментарий: «# font-src / base-uri / form-action / object-src — не ослабляют E2 (ужесточение).»
- nginx.conf, заголовок: «… img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; …» (add_header … always).
- nginx.conf, уровень server: add_header X-Content-Type-Options "nosniff" always; (и Referrer-Policy, Permissions-Policy).
- Статика: location ~* \.(js|css|…|ico|webp)$ со своим add_header Cache-Control → заголовки server (nosniff, CSP и прочие)
  на .js/.css сейчас не приходят. Каталога public/ и файла favicon нет.
- Правило nginx: add_header внутри location отменяет наследование ВСЕХ add_header уровня server (включая CSP).

## 5. ЧТО ПРОЧИТАТЬ
docs/process/CODER.md 11,1 КБ; AGENT-BRIEF.md 11,2; docs/STATE.md ≈ 10; эта карточка ≈ 5;
apps/miniapp/nginx.conf 8,9. **Чтение КОДЕРА ≈ 46 КБ.** Не читать: src/**, Dockerfile, docs/DEFECTS-*.md.

## 6. Файлы (1 + STATE)
Изменить: apps/miniapp/nginx.conf.

## 7. Контракт
- Заголовок CSP: «font-src 'self' data:;» → «font-src 'self';». Остальные директивы — байт в байт как были; одна строка.
- Комментарий: строку «font-src / base-uri / … (ужесточение).» заменить на:
    # font-src 'self' / base-uri 'self' / form-action 'self' / object-src 'none' — строже E2 (D-20 = А, 04.10).
    # Шрифтов в сборке нет; появятся — font-src правится в той же задаче (без data:, только 'self').
- Новый location ПЕРЕД location статики:
    # favicon.ico: файла нет; 204 без лога вместо 404 на каждое открытие Mini App.
    # add_header здесь НЕ писать: иначе nginx не унаследует заголовки server (CSP и прочие).
    location = /favicon.ico {
        access_log off;
        log_not_found off;
        return 204;
    }
- location статики (~* \.(js|css|…)$): рядом с его add_header Cache-Control добавить ОДНУ строку
    add_header X-Content-Type-Options "nosniff" always;
  CSP туда НЕ добавлять (CSP действует на документ, не на .js/.css). expires, Cache-Control, access_log — как были.

## 8. БД: нет.

## 9. Тесты
check.sh miniapp (tsc, vitest, build). CI: docker miniapp (nginx -t выполняется при старте в живой проверке).

## 10. Живые проверки (после мержа; СЕРВЕРНЫЙ + Автор)
1. pull → up -d --build miniapp → 6/6 (или 7/7 после projector-3) Up, healthy; docker compose exec miniapp nginx -t → ok.
2. curl -sI http://127.0.0.1:5173/ | grep -i content-security-policy → есть, font-src 'self'; без «data:» в font-src
   (img-src data: остаётся — это E2).
3. curl -sI http://127.0.0.1:5173/favicon.ico → HTTP 204 И есть заголовок Content-Security-Policy.
4. curl -sI http://127.0.0.1:5173/<любой .js из assets> → есть X-Content-Type-Options: nosniff
   (имя файла взять из index.html: curl -s http://127.0.0.1:5173/ | grep -o 'assets/[^"]*[.]js' | head -n 1).
5. Автор: закрыть Mini App полностью (кэш) → открыть → онбординг/finished открывается; logs miniapp без 404 favicon.

## 11. Запреты
AGENT-BRIEF §3. Плюс: CSP не ослаблять, новых источников и директив не добавлять; в location = /favicon.ico — без add_header;
location статики — только эта строка (nosniff), CSP туда не добавлять; прокси не трогать; файлов favicon не добавлять;
docs/DEFECTS-*.md не читать и не править.

## 12. Готово, когда
check.sh miniapp зелёный; CI 7/7; живая проверка 1–5.

## 13. Оценка
Часы Автора ~0,3; запросов КОДЕРА 1; кредиты 0 (Р0+).

## 14. РЕВЬЮЕР: нет — обоснование
Раздел 14 DESIGNER: initData, 18+, согласия (B-2), rate-limit (B-1), роли/GRANT (B-3), оплата. CSP — не из этого списка;
правка только сужает политику (убирает источник), favicon — пустой ответ без новых источников, в статику добавляется
только запрещающий заголовок nosniff.
Условие: КОДЕР добавляет источник или директиву CSP или add_header в новый location → ставим «да».
