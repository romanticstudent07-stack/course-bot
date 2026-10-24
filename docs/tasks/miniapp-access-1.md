# miniapp-access-1 — Mini App: экран «доступ не открыт» (no_access и 403 ACCESS_NOT_GRANTED)

Пачка Р-2, карточка (в2). Начинать после мержа api-access-1 (#126, main 71948d5).
API и бот не трогать. Выкат — вместе с api и bot после 25.10, по заданию ШТАБа.

## 1. Паспорт
- id: miniapp-access-1 · режим: Агент (платный) · срок: до вечера 24.10.
- Зависит от: db-access-1 (#124), bot-access-1 (#125), api-access-1 (#126) — все в main.
- Ветка: feat/miniapp-access-1.
- Коммит: «feat(miniapp): экран доступа не открыт при no_access и 403 (miniapp-access-1)».
- PR: «miniapp-access-1: экран доступа не открыт, проверить ещё раз (Р-2)».

## 2. Цель
- GET status ответил {"status":"no_access"} → отдельный экран до онбординга. Онбординг не
  монтируется, номера нет, черновик не открывается.
- POST first-launch ответил 403 ACCESS_NOT_GRANTED → тот же экран. Сейчас там «Что-то пошло
  не так» и «Повторить», который снова шлёт тот же POST и снова получает 403 (круг).
- Кнопка «Проверить ещё раз» → снова один GET status: доступ выдан → онбординг с начала.

## 3. Решения (К-6)
- «Тот, кому доступ не выдан, видит нейтральный экран «доступ не открыт» и участником не
  становится» [STATE Р-2; R-2026-10-1 Р-2 п.8].
- status → 200 {"status":"no_access"}; first-launch без доступа → 403 ACCESS_NOT_GRANTED
  [Автор 23.10, ответ 6; docs/tasks/api-access-1.md §1–§2].
- Текст экрана (заглушка на «Вы», дословно): «Доступ пока не открыт. Если у Вас есть
  промокод — отправьте его боту. Когда бот ответит, нажмите «Проверить ещё раз».»
  Кнопка: «Проверить ещё раз». [решил ШТАБ, З2 (09-communications: «Вы», «факт + путь», без
  вины; Р-2 п.8); заглушки на «Вы» — Автор, ответ 2; слово «промокод» — как ACCESS_PROMPT
  в bot/texts.py, #125]
- Ссылки и кнопки «Открыть бота» нет, новых переменных нет [решил ШТАБ, канон молчит;
  ссылка — позже, miniapp-fix-2].
- Текст — заглушкой прямо в коде, как тексты экрана «Повторить», не через text_registry
  [решил ШТАБ, З2; расхождение с каноном — DEFECTS D-39].
- 403 ловит App через новый проп onSubmitError у OnboardingFlow; screenAfterError не менять
  [ШТАБ, З2: так нет круга импортов startup.ts ↔ OnboardingFlow.tsx].
- РЕВЬЮЕР не нужен: гейт держит сервер (#126), клиент только показывает экран [ШТАБ, З2].

## 4. Выдержки
- R-2026-10-1 Р-2 п.8 — цитата в разделе 3.
- api-access-1 §2: «Проверка — в транзакции first-launch, после возраста и согласий,
  до get_or_create». Значит, несовершеннолетний получит 403 AGE_GATE_UNDERAGE раньше,
  чем 403 ACCESS_NOT_GRANTED, и экран underage работает как раньше.
- build/miniapp-screens.md: «Каждый экран → id + путь + … ключи текстов из text_registry»;
  шапка — «скелет v0», раздел «Долги» — «Ключи text_registry не сгенерированы». Экрана
  «доступ не открыт» в инвентаре нет.

## 5. ЧТО ПРОЧИТАТЬ (чтение Агента ≈ 87 КБ)
AGENT-BRIEF.md 17,1 · docs/STATE.md 21,2 (только раздел «Сейчас») · эта карточка ≈ 9 ·
apps/miniapp/src/api/client.ts ≈ 10 · apps/miniapp/src/components/startup.ts 2,8 ·
apps/miniapp/src/components/startup.test.ts 4,0 · apps/miniapp/src/components/App.tsx 5,8 ·
apps/miniapp/src/components/OnboardingFlow.tsx 16,7.
Больше ничего не открывать. OnboardingFlow.test.ts не менять и не читать.

## 6. Файлы (все — изменить, ровно 6)
1. apps/miniapp/src/api/client.ts — в тип OnboardingStatus добавить { status: 'no_access' }.
   Комментарии: у getOnboardingStatus — «200 no_access (Р-2)», у postFirstLaunch —
   «403 ACCESS_NOT_GRANTED — доступ не выдан (Р-2)». Логику не менять.
2. apps/miniapp/src/components/startup.ts:
   - StartPhase = 'number' | 'onboarding' | 'no-access';
   - isNoAccess(resp: unknown): boolean — true только для объекта со status === 'no_access';
   - startPhase: returning с short_no → 'number'; isNoAccess → 'no-access'; иначе 'onboarding';
   - isAccessNotGranted(err: unknown): boolean — err instanceof ApiError, status 403 и
     code 'ACCESS_NOT_GRANTED'. ApiError импортировать из '../api/client.ts';
   - export const NO_ACCESS_TEXT и NO_ACCESS_BUTTON — тексты из раздела 3 дословно;
   - шапку файла дополнить строкой про no_access.
3. apps/miniapp/src/components/startup.test.ts — тесты из раздела 9.
4. apps/miniapp/src/components/OnboardingFlow.tsx:
   - в OnboardingFlowProps добавить необязательный onSubmitError?: (err: unknown) => boolean
     с комментарием «true — ошибку обработал App, компонент ничего не показывает»;
   - в catch у submit первой строкой: if (onSubmitError?.(err)) return;
     finally остаётся. onSubmitError — в зависимости useCallback;
   - startup.ts не импортировать (будет круг импортов). Больше ничего не менять.
5. apps/miniapp/src/components/App.tsx:
   - Phase дополнить 'no-access';
   - в then у status: startPhase(resp) === 'no-access' → setPhase('no-access') и return,
     до setReconsent. openDraft не вызывать;
   - фаза no-access: та же разметка, что у start-error, — p с NO_ACCESS_TEXT и кнопка
     NO_ACCESS_BUTTON, onClick={retry} (есть уже: checking → один GET status);
   - у OnboardingFlow проп onSubmitError={(err) => { if (!isAccessNotGranted(err)) return
     false; setPhase('no-access'); return true; }}. OnboardingFlow размонтируется, дата
     рождения уходит из памяти;
   - шапку файла дополнить описанием фазы no-access.
6. docs/STATE.md — ТОЛЬКО одна строка в конец раздела «Сейчас»; остальное не трогать
   (файл больше 20 КБ, сжатие — отдельным docs-PR):
   - miniapp-access-1 (24.10): Mini App — экран «доступ не открыт» при status no_access и при 403 ACCESS_NOT_GRANTED из first-launch, кнопка «Проверить ещё раз» → снова GET status; выкат — вместе с api и bot после 25.10 (задание ШТАБа).

## 7. Контракт (Mini App только читает)
- GET /miniapp/v1/onboarding/status → 200 {"status":"no_access"}; прочие ответы — как были
  (returning, reconsent, new; 401, 429, 503).
- POST /miniapp/v1/onboarding/first-launch → 403, code ACCESS_NOT_GRANTED. По коду client.ts
  это ApiError(403, 'ACCESS_NOT_GRANTED', …). Прочие ошибки — как были.

## 8. БД
Нет.

## 9. Тесты (vitest, environment node; только startup.test.ts)
- startPhase({status:'no_access'}) → 'no-access'; returningShortNo → null.
- {status:'no_access', short_no:'#000001'} → 'no-access' (номер не показывается).
- Старые тесты startPhase проходят как есть: returning → number; reconsent, new,
  неизвестный status, битое тело → onboarding.
- isNoAccess: true только для {status:'no_access'}; false для new, returning, null,
  строки 'no_access', [].
- isAccessNotGranted: ApiError(403,'ACCESS_NOT_GRANTED') → true; ApiError(403,
  'AGE_GATE_UNDERAGE'), ApiError(401,'ACCESS_NOT_GRANTED'), ApiError(500,'HTTP_ERROR'),
  TypeError, null → false.
- isReconsent({status:'no_access'}) → false.
- NO_ACCESS_TEXT и NO_ACCESS_BUTTON равны строкам из раздела 3.
Цель: bash tools/check.sh miniapp (tsc --noEmit + vitest). Действующие проверки D-19 и R342
в OnboardingFlow.test.ts (хранилища, console, innerHTML в App.tsx и client.ts) должны остаться
зелёными. Только CI: сборка образа miniapp.

## 10. Живая проверка (после мержа и выката api + bot + miniapp, после 25.10)
- ДО выката: тестовый аккаунт без доступа жмёт /start в боте. Mini App НЕ открывать:
  старый API создаст pid.
- По коду до #125 бот на /start ставил кнопку меню Mini App лично в чат
  (handlers.py, set_chat_menu_button). Сохранится ли она в новом боте — не проверено;
  сервер сверит до выката.
- После выката: аккаунт открывает Mini App кнопкой меню → сразу экран «Доступ пока не
  открыт…» (без 18+, согласий и номера) → «Проверить ещё раз» → тот же экран.
- Аккаунт пишет промокод боту → Автор нажимает «Выдать» → «Проверить ещё раз» → онбординг
  с приветствия → first-launch 200 → номер.
- БД: у аккаунта до выдачи доступа нет участника; после выдачи — один.
- Развилка: личной кнопки нет и Mini App открыть нечем → экран «без доступа» не проверяем,
  записываем в STATE «перенесено»; проверяем только путь после выдачи доступа (#125).
- Экран при 403 из first-launch вживую не воспроизвести (status отвечает раньше) — его
  закрывают тесты раздела 9.

## 11. Запреты
- AGENT-BRIEF.md, раздел 3, целиком. Только 6 файлов из раздела 6; apps/api, apps/bot,
  docs/architecture, .github не трогать.
- Ничего не хранить на устройстве (status, флаг no_access). Без console, без новых
  зависимостей, без initDataUnsafe.
- Тексты — дословно из раздела 3, без ссылки на бота и без новых env.
- screenAfterError, errorMessage и OnboardingFlow.test.ts не менять.

## 12. Критерии готовности
- check.sh miniapp зелёный, CI зелёный; файлов ровно 6; в STATE добавлена одна строка.
- no_access не монтирует OnboardingFlow (нет запроса /texts/bulk) и не открывает черновик.
- 403 ACCESS_NOT_GRANTED → экран no-access; прочие ошибки first-launch — как раньше.
- Отличия от карточки перечислены в описании PR.

## 13. Оценка
- Кредиты: 300–500 (потолок 700). Часы Автора: ≈ 0,5.
- Общий эндпоинт не меняется — чинка чужих тестов не ожидается (урок api-access-1).
- CI НЕ ЖДАТЬ: после push сразу ИТОГ и конец; gh run watch и опрос проверок запрещены.

## 14. РЕВЬЮЕР
Нет: гейт держит сервер (#126), Mini App только показывает экран [ШТАБ, З2].
