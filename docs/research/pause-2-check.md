# pause-2-check — сверка pause-2 §9 по коду (ШТАБ, 15.11.2026)
Hash 8b1ae62. Правило К — docs/process/CANON-CHECK.md. Основа — docs/research/pause-2.md §9.
Для окон КАРТОЧКИ T1, T1b, T6a, T6c, T7 — читать вместе с pause-2.md; где расходятся — верен этот файл.

## 1. Итог по пунктам §9
1. access_grants: PRIMARY KEY (tg_user_id); других UNIQUE нет, кроме частичного uq_access_grants_admin_message_id; статусы pending / granted / denied; колонки pid нет (по коду: 0010_access_grants.py; apps/bot/bot/access.py — ON CONFLICT (tg_user_id)). Вторая строка на того же человека невозможна.
   Решил ШТАБ (К-5): пункт pause-2 §6 «access_grants: purpose, pid» из 0018 убрать. Заявки рестарта — своя таблица, миграция 0020 в T6c; гейт Р-2 и access.py не меняются. Строку pause-2 §5 «access_grants (purpose restart; requested → granted)» карточка T6c заменяет.
2. Повтор дня: ключи day_done, day_close, day_queue, tasks_open, ladder, ladder_day2 содержат dsa(day_started_at); PK day_marks — (pid, day_started_at, block_id); в reflections_log UNIQUE нет. Новый day_started_at конфликтов не даёт (по коду: day_keys.py, 0008, 0011).
   Без даты — только day_enter:{pid}: reissue_day не должна идти через day_entered. noon:{pid}:{местная дата}: перевыдача в те же сутки после НП1 — второго НП1 нет (норма В5 А).
3. participant_state.status_flags — text[] NOT NULL DEFAULT '{}', CHECK нет (0001); CHECK lifecycle_phase уже включает sleeping (0005). 0018 их не трогает.
4. «Часы» — внутри run_forever проектора (life_ops.tick, notify_ops.tick), роль app_projector (projector.py). Перевода approved → active сейчас нет нигде.
   Решил ШТАБ (К-5): в 0018 app_projector получает UPDATE (status, stage_no, restart_no, ended_at) на participant_pauses — вместо «роль часов — по коду» в pause-2 §6.
5. Бот: человеку со статусом granted classify даёт NOTHING — текст молча пропускается (access.py). Рестарт — новая ветка: granted и в participant_state есть флаг block_lives (SELECT participant_state для app_bot — уже в pause-2 §6).
6. Дата начала годового цикла пауз отдельно не хранится.
   Решил ШТАБ (К-5): cycle_start_at = 00:00 по поясу участника в дату первой активации кнопок (04:00) первого дня; первый день — событие day_entered с наименьшим id. Функцию day_clock для этой даты ПРОЕКТИРОВЩИК называет по коду (day_clock.py ШТАБ целиком не дочитал — не проверено).
7. Бэкфилл pause_budgets в 0018: участникам с day_entered — cycle_start_at по п.6, остаток 14, restart_no 0. Без day_entered строку создаёт проектор в T2.
8. Будущий day_started_at: по прочитанному коду до 04:00 той даты окно not_active, is_overdue ложно — life_ops не закрывает день и не списывает жизнь; НП1 ждёт window = open (day_clock.py, life_ops.py, notify_ops.py). Отдельный флаг не нужен. notify_ladder.py не читан — не проверено; в T6a обязательны тесты.
9. Сейчас в sleeping — 0: отчёт сервера 15.11 — А1 фаза onboarding, lives 1; А2–А4 к заданиям не приступали (Автор 15.11); Автор сдаёт отчёт за А1 каждый день (SHTAB-DEBTS §0). Бэкфилл block_lives в T6a — страховка на 0 строк; пункт «число sleeping» из Г0 снят.
10. Команды revive в реестре 34 команд нет; /life и /revert есть (build/bot-commands-registry.yaml) → правка реестра (DOCS) в T7.

## 2. Решение Автора 15.11 (К-6: [Автор, канон молчит])
НП3 «Задания откроются … в 04:00» отправляется и после перевыдачи дня: выход из sleeping, revive, рестарт, /revert — вариант А.
Канон: проверено notify_ops.py (НП3 А — после очереди и после онбординга), pause-2 §8 А1 — молчит.
Следствие (по коду notify_ops.py): сейчас НП3 запускается по ключу day_queue или по событию day_entered с at = D; reissue_day не даёт ни того, ни другого → в T6a третий запуск НП3 по событию перевыдачи (новый D в событии). notify_ops.py (22,4 КБ) и его тесты входят в T6a; оценку T6a ПРОЕКТИРОВЩИК пересчитывает.

## 3. Для карточек
- T1 (0018): без access_grants (п.1); UPDATE для app_projector (п.4); бэкфилл pause_budgets (п.6–7).
- T1b (0019): как в pause-2 §6.
- T6a: reissue_day не через day_entered (п.2); третий запуск НП3 (§2); тесты «будущий day_started_at — без закрытия дня, без НП1, без лестницы» (п.8); бэкфилл block_lives (п.9).
- T6c: таблица заявок рестарта, миграция 0020 (п.1); ветка «granted + block_lives» в боте (п.5).
- T7: revive — в реестр команд (п.10).
