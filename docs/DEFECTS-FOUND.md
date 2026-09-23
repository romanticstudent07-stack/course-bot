# DEFECTS-FOUND.md — расхождения архитектуры с реальностью

Сюда агент пишет расхождения, найденные при реализации.

**НЕ править `docs/architecture/**`** — это read-only зеркало.
Все правки архитектуры делаются в репо DOCS-course-bot.

## Формат записи

## D-N. Краткое название

- **Файл архитектуры (зеркало):** `docs/architecture/…`
- **Файл реализации:** `apps/…`
- **Суть расхождения:** описание что не сходится.
- **Предлагаемое решение:** что предлагает агент.
- **Ждём решения Автора:** да/нет.

---

## D-1. Блок 15: доставка медиа

- **Файл архитектуры (зеркало):** `docs/architecture/build/DIVISION.md`,
  `docs/architecture/15-content-antipiracy.md` (и подпапка `15/`).
- **Файл реализации:** пока не создан.
- **Суть расхождения:** DIVISION.md говорит, что Mini App отдаёт медиа
  через pre-signed URL. Блок 15 (антипираттство) утверждает,
  что видео и материалы курса живут только во внешнем публичном
  Telegram-канале, бот не хостит медиа и не отдаёт `file_id`.
  Схемы «pre-signed URL» и «внешний Telegram-канал» противоречат друг другу.
- **Предлагаемое решение:** Автору определить, какой источник медиа —
  S3 pre-signed URL для собственного хостинга или внешний Telegram-канал.
- **Ждём решения Автора:** да.

## D-2. CSP: три разные редакции в зеркале

- **Файл архитектуры (зеркало):** `normative/errata-unified.md` (E2 `csp_final`),
  `build/miniapp-frontend-stack.md`, `build/miniapp-api-contract.yaml` (комментарий в конце).
- **Файл реализации:** `apps/miniapp/nginx.conf`.
- **Суть расхождения:** E2 разрешает `script-src 'self' https://telegram.org`
  и `frame-ancestors https://web.telegram.org https://telegram.org`. В build-файлах
  указаны `script-src 'self'`, `connect-src 'self' https://api.telegram.org`
  и `frame-ancestors https://web.telegram.org https://t.me`.
- **Решение агента:** взята редакция E2 (у ERRATA высшее старшинство). Домен
  `{s3-domain-ru}` не подставлен: это плейсхолдер-шлюз, решение Автора.
- **Ждём решения Автора:** да — нужно ли выровнять build-файлы в DOCS-course-bot.

## D-3. Остатки MinIO и версия Garage в документах

- **Файл архитектуры (зеркало):** `build/build-order.md` (Итерация 0-А: «MinIO», `minio-init`).
- **Файлы вне зеркала:** `.genspark/rules.md` (хосты `minio:9000`),
  `infra/SERVER-IRONCLAD.md` (`dxflrs/garage:v2.1.0`, а в compose и README — `v2.3.0`).
- **Суть расхождения:** MinIO устарел, код использует Garage (`http://garage:3900`).
- **Решение агента:** в коде только Garage. Документы не правились:
  зеркало read-only, а `.genspark/**` без обоснования не трогаем.
- **Ждём решения Автора:** да — правка в DOCS-course-bot и в `.genspark/rules.md`.

## D-4. Кто принимает Telegram webhook

- **Файл архитектуры (зеркало):** `build/DIVISION.md` (backend: «Обработчик Telegram Webhook»).
- **Файлы реализации:** `apps/bot/bot/app.py`, `infra/README.md` (шаг 8: `setWebhook` → `/webhook/telegram`).
- **Суть расхождения:** по DIVISION апдейты принимает backend, но диспетчер
  aiogram живёт в `apps/bot`. Контракт передачи апдейтов api → bot не описан.
- **Решение агента:** в Итерации 0-А бот работает на long polling (входящий порт
  не нужен). Если webhook зарегистрирован, бот его не удаляет, а пишет ошибку в лог.
- **Ждём решения Автора:** да.

<!-- следующие записи (D-5, ...) добавляет агент по мере обнаружения -->
