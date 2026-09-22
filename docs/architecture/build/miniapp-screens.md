---
file: build/miniapp-screens.md
block: "—"
title: "Инвентарь экранов Mini App"
status: скелет (наполняется Автором)
doc_version: "скелет v0"
---

# Инвентарь экранов Mini App

Каждый экран → id + путь + краткое описание + состояние из FSM + ключи текстов из `text_registry` + переходы. Ключи `text_registry` — формат `{домен}.{имя}` из И4.

## Онбординг (SEAM-1)

| id | Путь | Что | Триггер входа | Ключи текстов | Выходы |
|---|---|---|---|---|---|
| `onb.welcome` | `/` | Приветствие + первичный дисклеймер | first-launch | `onb.welcome.title`, `onb.welcome.disclaimer` | → `onb.age-gate` |
| `onb.age-gate` | `/onboarding/age` | Ввод даты рождения (жёсткая проверка ≥ 18) | onb.welcome | `onb.age.title`, `onb.age.error_under18` | → `onb.consent-152fz` |
| `onb.consent-152fz` | `/onboarding/consent/152fz` | Согласие 152-ФЗ (C1) | onb.age-gate | `legal.consent.152fz` | → `onb.offer` |
| `onb.offer` | `/onboarding/offer` | Оферта + галочка «согласен» (C2) | onb.consent-152fz | `legal.offer` | → `onb.payment` |
| `onb.payment` | `/onboarding/payment` | Оплата первого этапа | onb.offer | `payment.first_stage_title` | → `onb.form` (после confirm) |
| `onb.form` | `/onboarding/form` | Анкета (ФИО, телефон, ТЗ, стартовые замеры, фото 4 стороны) | onb.payment | `onb.form.*` | → `onb.checkup` |
| `onb.checkup` | `/onboarding/checkup` | Чек-Ап (Блок 5) | onb.form | `checkup.*` | → `onb.rules` |
| `onb.rules` | `/onboarding/rules` | Правила + «Ознакомлен/Принимаю» | onb.checkup | `onb.rules` | → `day.current` (день 1.1) |

## Дневной модуль (Блок 3)

| id | Путь | Что |
|---|---|---|
| `day.current` | `/day` | Экран текущего дня, чек-лист заданий, кнопка «Отправить отчёт» |
| `day.reflection-06` | `/day/reflection/6` | Рефлексия дня 6 (диагностическая) |
| `day.reflection-13m` | `/day/reflection/13m` | Рефлексия-Переход (без оплаты) |
| `day.reflection-13p` | `/day/reflection/13p` | Рефлексия-Рубеж (с оплатой) |

## Карточка участника (сторона Участника, Блок 6)

| id | Путь | Что |
|---|---|---|
| `me.card` | `/me` | Моя карточка (данные, замеры, позиция, жизни) |
| `me.consents` | `/me/consents` | Мои согласия C0–C6, отзыв C5 (фото) |
| `me.change-map` | `/me/change-map` | Полная Карта изменений (антропометрия / фото / самочувствие / функциональные) |
| `me.legal-data` | `/me/legal` | Юр.данные, экспорт (`/miniapp/v1/export/request`) |
| `me.settings-notifications` | `/me/notifications` | Настройки уведомлений (чекбоксы reminders / motivational, P-5) |

## Жизненный цикл (Блок 10)

| id | Путь | Что |
|---|---|---|
| `lifecycle.start` | `/start-btn` | Кнопка [Старт] (порядок гейтов: возраст → правовое → оплата) |
| `lifecycle.paused` | `/paused` | Экран паузы (три полосы паузы, ETA) |
| `lifecycle.returned` | `/returned` | Экран возвращения после долгой паузы |

## Хранение и доставка (Блок 15)

| id | Путь | Что |
|---|---|---|
| `content.material` | `/content/:id` | Просмотр материала (deep-link из бота), pre-signed URL, порог 10 МБ (И4) |
| `content.photo-submit` | `/content/photo` | Отправка фото 4 сторон (multipart + `client_op_id`) |

## Оплата и возврат (Блок 16)

| id | Путь | Что |
|---|---|---|
| `payment.pay` | `/payment/pay` | Форма оплаты (виджет PSP) |
| `payment.refund` | `/payment/refund` | Заявка на возврат |
| `payment.act` | `/payment/act/:id` | Акт об оказании услуг (после Refund Saga) |

## Служебные экраны

| id | Путь | Что |
|---|---|---|
| `error.401` | `/error/401` | initData невалидна или устарела → просьба переоткрыть Mini App |
| `error.403` | `/error/403` | Whitelist-only route открыт не-владельцем |
| `error.404` | `/error/404` | Нет маршрута |
| `error.maintenance` | `/maintenance` | `/panic_maintenance` активен (Б17) |

## Долги

- Ключи `text_registry` не сгенерированы — задел под `config/text_registry.yaml`.
- Дизайн-макеты (Figma) не приложены — задел Автора.
- Локализация: пока только ru-RU; en/de/…  — при расширении.
