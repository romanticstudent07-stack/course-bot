# returning-2 — Mini App: вернувшийся сразу видит свой номер

## 1. Паспорт
- id: returning-2 · PR: «returning-2: старт по /onboarding/status, без метки finished»
- Ветка: feat/returning-2 · Режим: Р0+ · Зависит от: returning-1.
- Начинать ТОЛЬКО после мержа И живой выкатки returning-1 (status отвечает на сервере).
- Область: только Mini App (apps/miniapp).

## 2. Цель
При открытии Mini App сначала спрашивает сервер (GET /miniapp/v1/onboarding/status).
«returning» → сразу экран с номером, экраны онбординга не монтируются. «new» и «reconsent» →
онбординг как сейчас. Метка finished на устройстве больше не хранится.

## 3. Решения Автора (дословно)
- 06.10, вариант А: «вернувшийся сразу видит номер; повтор экранов только при отзыве согласия /
  новой ver_of_text / erased». Срок отсутствия НЕ критерий.
- З1 вопрос 2 — Б: после номера незаконченный черновик моложе 24 ч → продолжить, иначе → в курс.
  Метку finished убрать.

## 4. Контракт сервера и выдержки
GET /miniapp/v1/onboarding/status (сделан в returning-1; DOCS ещё не правлен — D-22, ШТАБ),
заголовок X-Telegram-Init-Data (как все запросы client.ts).
200 — одна из форм: {"status":"returning","short_no":"#000001"} | {"status":"reconsent",
"reasons":[...]} | {"status":"new"}. Ошибки: 401, 429, 503 (тело {code, message}).
Решение принимает сервер; клиент версии и тексты согласий не сравнивает.
first-launch по-прежнему 201 {pid, short_no}; при reconsent он сам допишет новые give.

OnboardingFlow.tsx — импорт в vitest (environment node) безопасен (проверено ПРОЕКТИРОВЩИКОМ:
OnboardingFlow.test.ts уже импортирует модуль в node). Импорты модуля — только:
    import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
    import { ApiError, newClientOpId, postFirstLaunch, postTextsBulk, type ConsentId,
      type FirstLaunchRequest, type TextsBulkResponse } from '../api/client.ts';
CSS нет; на верхнем уровне — только объявления (обращения к SDK — внутри функций client.ts).
Выдержка — errorMessage (экспорт OnboardingFlow.tsx, дословно):
    /** Понятное сообщение для экрана ошибки (401 / 429 / 503 / сеть / прочее). */
    export function errorMessage(err: unknown): string {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          return 'Не удалось подтвердить вход через Telegram. Нажмите «Повторить» или откройте приложение заново.';
        }
        if (err.status === 429) return 'Слишком много попыток подряд. Подождите минуту и нажмите «Повторить».';
        if (err.status === 503) return 'Сервис временно недоступен. Попробуйте чуть позже.';
        return 'Что-то пошло не так. Нажмите «Повторить».';
      }
      return 'Не удалось связаться с сервером. Проверьте интернет и нажмите «Повторить».';
    }

## 5. ЧТО ПРОЧИТАТЬ (целиком)
- apps/miniapp/src/api/client.ts — 5 КБ (меняется)
- apps/miniapp/src/components/App.tsx — 2 КБ (меняется)
- apps/miniapp/src/components/drafts.ts — 9 КБ (меняется)
- apps/miniapp/src/components/drafts.test.ts — 9 КБ (меняется)
- apps/miniapp/src/components/LaterSteps.tsx — 13 КБ (только комментарии про finished)
Код ≈ 38 КБ + CODER.md 11 + AGENT-BRIEF.md 11 + STATE.md 16 + карточка ≈ 12.
Итог чтения КОДЕРА ≈ 88 КБ. OnboardingFlow.tsx (17 КБ) НЕ читать и НЕ менять: нужное — в §4.

## 6. Файлы
- создать: apps/miniapp/src/components/startup.ts — чистые функции решения (без React)
- создать: apps/miniapp/src/components/startup.test.ts
- изменить: client.ts, App.tsx, drafts.ts, drafts.test.ts, LaterSteps.tsx (комментарии)

## 7. Логика
### 7.1 client.ts
- type OnboardingStatus = {status:'returning'; short_no:string} | {status:'reconsent';
  reasons:string[]} | {status:'new'}; getOnboardingStatus() → apiRequest GET
  '/miniapp/v1/onboarding/status' (без clientOpId: запрос ничего не меняет).
### 7.2 startup.ts (чистые функции, тестируются в node)
- startPhase(resp: unknown): 'number' | 'onboarding'. 'number' — только если status ===
  'returning' и short_no — непустая строка. reconsent, new, неизвестный status, битое тело →
  'onboarding' (безопасная сторона: экраны согласий, решение снова за сервером).
- afterNumber(draft: Draft | null): 'later' | 'app'. 'later' — черновик есть и step !== 'finished';
  иначе 'app'. (openDraft уже чистит чужой, битый и старше 24 ч.)
- startErrorMessage(err) = errorMessage(err) из OnboardingFlow.tsx (§4): 401 → текст про вход
  через Telegram, 429, 503, сеть — те же формулировки, что сейчас.
### 7.3 App.tsx — фазы: checking → number | onboarding → later | app; плюс start-error
- checking (первая фаза): «Загрузка…», ничего другого (block_all_ui_until_checked); один вызов
  getOnboardingStatus при монтировании (флаг cancelled, как в LaterSteps).
- number: «Ваш номер участника: <short_no>» и кнопка «Продолжить». Без запроса текстов (строка
  интерфейса, не текст курса). «Продолжить» → openDraft(store, tgUserId, Date.now()) (ошибка
  хранилища → null) → afterNumber → later | app.
- В фазах checking, number, start-error OnboardingFlow НЕ монтируется вообще (он шлёт
  /texts/bulk при монтировании) — проверяется по коду App.tsx и РЕВЬЮЕРОМ.
- onboarding: OnboardingFlow как сейчас. onComplete: если старт был 'new' → later (как сейчас);
  если старт был reconsent → то же правило, что после номера (openDraft → afterNumber).
- start-error (любая ошибка status): текст startErrorMessage и кнопка «Повторить» →
  снова checking. Отдельного экрана для 401 в Mini App сейчас нет (EnvUnsupported — только
  когда не внутри Telegram, index.tsx), поэтому 401 → этот же экран «Повторить».
- Ошибка status НИКОГДА не ведёт в онбординг и не показывает номер.
### 7.4 drafts.ts — метки finished на устройстве больше нет
- finishDraft: всегда store.clear() (и при известном, и при неизвестном пользователе); ошибка
  хранилища глотается без лога; onFinish ровно 1 раз — как сейчас. FINISHED_DRAFT удалить.
- saveDraft со step 'finished' → store.clear() вместо записи (экран «Анкета заполнена» не
  оставляет email и город на устройстве).
- openDraft: запись со step 'finished' (старые устройства) → clear и null.
- Тип LaterStep и шаг 'finished' в LATER_STEPS остаются: это экран, а не хранимая метка.
- Комментарии вверху drafts.ts и LaterSteps.tsx — обновить под новые правила.

## 8. БД — нет.

## 9. Тесты (check.sh miniapp; vitest environment node)
startup.test.ts:
1. startPhase: returning с short_no → number; returning без short_no / пустой → onboarding;
   reconsent → onboarding; new → onboarding; {status:'x'}, null, строка → onboarding.
2. afterNumber: null → app; {step:'finished'} → app; {step:'email'} → later; {step:'offer'} → later.
3. startErrorMessage: ApiError 401 → текст про вход через Telegram; 429; 503; TypeError (сеть).
drafts.test.ts (тесты метки finished переписать):
4. finishDraft с известным пользователем → хранилище пусто (peek() === undefined), onFinish 1 раз.
5. finishDraft при reject хранилища → onFinish 1 раз, без исключения.
6. saveDraft со step 'finished' → хранилище пусто.
7. openDraft с сохранённой записью step 'finished' → null и хранилище пусто.
8. Остальные тесты drafts (24 ч, чужой tg_user_id, битая запись, без даты рождения) — зелёные.
Только CI: сборка Docker miniapp, guard eol.

## 10. Живые проверки (Автор в Telegram, tailnet; СЕРВЕРНЫЙ пересобирает miniapp)
1. Автор (returning по SQL из returning-1) открывает Mini App → «Загрузка…» → сразу номер #000001,
   без welcome, 18+ и C1. Лог api: одна строка status=returning, first-launch НЕ вызывался.
2. «Продолжить» → курс (черновика нет) или незаконченный шаг анкеты (если был моложе 24 ч).
3. Пройти анкету до «Перейти к курсу», закрыть, открыть → номер → сразу курс.
4. Негатив (по желанию, если ШТАБ даст способ): ошибка сети → экран «Повторить», не онбординг.
5. CSP-репортов нет; 4 healthy.

## 11. Запреты
- AGENT-BRIEF §3. Не менять OnboardingFlow.tsx, порядок его шагов и first-launch.
- Клиент не решает «пускать ли» сам: ни по initDataUnsafe, ни по черновику, ни по времени.
- Не хранить на устройстве short_no, status, reasons, дату рождения. Новые зависимости — нет.
- docs/DEFECTS-FOUND.md не менять (D-22 — задача ШТАБа CB-docs-3).

## 12. Готово, когда
CI 7/7; тесты 1–8; живые проверки §10 пункты 1–3 пройдены.

## 13. Оценка: Автор ~0,6 ч (КОДЕР 1 окно, CI 1–2 круга, РЕВЬЮЕР 1 окно); кредиты 0.

## 14. РЕВЬЮЕР: ДА — ветка решает, показывать ли экраны 18+ и согласий (B-2) и что делать
при 401 (initData). Проверить: при любой ошибке status не попасть ни в номер, ни мимо согласий.
