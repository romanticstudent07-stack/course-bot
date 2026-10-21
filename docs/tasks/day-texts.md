# day-texts — тексты-заглушки экрана /day (B9.day_*)

## 1. Паспорт
- id: day-texts · область: тексты API (apps/api/config/texts) · режим: Р0 (Автор, сайт GitHub, 1 файл).
- Заголовок PR: feat(texts): day-texts — заглушки B9.day_active_from_hint, B9.day_queue_wait, B9.day_closed_hint
- Ветка: feat/day-texts · Зависит от: мержа карточек (docs/tasks-day-screen). Дальше: day-screen-a.
- Миграций нет, таблиц 15. Кредиты 0.

## 2. Цель
Добавить в text_registry три ключа экрана /day: подсказка «кнопки станут активны», ожидание очереди,
закрытый день. Только заглушки (репо публичный до 0-Б). Экран day-screen-a берёт их через /texts/bulk.

## 3. Решения (З2, 21.10, сверено ШТАБом)
- Ключи — B9.day_* (Day.* не проходит схему): B9.day_active_from_hint, B9.day_queue_wait, B9.day_closed_hint.
- legal_status pre-legal-review; тон closed_hint — по DM 3.20, очередь — по DM 3.19.
- Меток {date} нет: в схеме подстановок нет (есть только plurals_ru). Дату и «04:00» экран выводит рядом сам.
- Отдельная задача Р0 до карточки a; на сервере: build migrate → texts load.

## 4. Выдержки
- build/config-schemas/text_registry.schema.json: key ^(B2|B4|B5|B7|B9|B10|B14|B15|B16|legal)\.[a-z][a-z0-9_]*$;
  обязательные key, tone (soft/neutral/strict), legal_status (pre-legal-review/approved), text (1–4096);
  version — SemVer, повышать при любой правке текста.
- DM 3.19 (03-day-mechanics.md): «Вы поставлены в очередь на модерацию»; задержка 10–60 минут.
- DM 3.20: «Наказание» → «возврат для закрепления»; «возвращаемся закрепить блок».
- STATE: новые тексты требуют пересборки migrate до texts load.

## 5. ЧТО ПРОЧИТАТЬ
apps/api/config/texts/day.json — 4,2 КБ (сейчас version 0.1.0, 18 записей B9.day_m1_*).

## 6. Файлы
- Изменить: apps/api/config/texts/day.json — version 0.1.0 → 0.2.0 и 3 новые записи в конце entries.

## 7. Правка на сайте
Шаг 1. Ты, GitHub (сайт): открой apps/api/config/texts/day.json в ветке main → значок карандаша.
Шаг 2. Там же: строку "version": "0.1.0", замени на "version": "0.2.0",
Шаг 3. Там же: последние 3 строки файла (это строки «    }», «  ]», «}») замени блоком ниже целиком.

        },
        {
          "key": "B9.day_active_from_hint",
          "tone": "neutral",
          "legal_status": "pre-legal-review",
          "text": "[ЗАГЛУШКА] Кнопки заданий станут активны:",
          "notes": "day-texts: экран /day. После текста экран сам выводит дату и время из active_from. Заглушки до 0-Б."
        },
        {
          "key": "B9.day_queue_wait",
          "tone": "soft",
          "legal_status": "pre-legal-review",
          "text": "[ЗАГЛУШКА] Вы поставлены в очередь на модерацию. Результат и задания следующего дня появятся здесь."
        },
        {
          "key": "B9.day_closed_hint",
          "tone": "soft",
          "legal_status": "pre-legal-review",
          "text": "[ЗАГЛУШКА] Приём отчёта за этот день завершён. Возвращаемся закрепить блок: день скоро откроется снова."
        }
      ]
    }

Шаг 4. Там же: Commit changes → «Create a new branch» → имя feat/day-texts → Propose changes → Create pull request.
Увидишь: в Files changed 1 файл, +23 строки примерно. Если CI красный (JSON или схема) — текст ошибки в ШТАБ.

## 8. БД
Нет (строки text_registry пишет texts load).

## 9. Тесты
Codespaces не нужен. CI 7/7 (тесты api проверяют seed по схеме). Мерж — после проверки ШТАБа.

## 10. Живые проверки (СЕРВЕРНЫЙ, после мержа)
- git pull; DC --profile tools build migrate (обязательно до texts load: образ migrate — 54ca133).
- texts load — командой из infra/SERVER-IRONCLAD.md, «Миграции и тексты (B-3d)» (DC --profile tools run --rm --no-deps migrate …).
- Ожидание: «загружено 3, лишних в БД 0» (обновлено — как в норме #100, ШТАБ сверит число).
- SQL под владельцем: SELECT key FROM text_registry WHERE key IN ('B9.day_active_from_hint','B9.day_queue_wait',
  'B9.day_closed_hint') → 3 строки. 7/7 Up, 5 healthy.

## 11. Запреты
Реальных текстов курса нет — только [ЗАГЛУШКА]. Прежние 18 записей не трогать. Других файлов в PR нет.

## 12. Готовность
1 файл; version 0.2.0; CI 7/7; на сервере texts load «загружено 3, лишних 0».

## 13. Оценка
Автор ≈ 0,2 ч + сервер 1 задание. Кредиты 0.

## 14. РЕВЬЮЕР: нет (тексты-заглушки, без кода).
