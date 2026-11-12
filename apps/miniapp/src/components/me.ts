// apps/miniapp/src/components/me.ts — чистые функции экрана me.card /me (miniapp-i3-2a §7.2).
//
// Без React и без запросов (тесты — vitest, environment node). Экран — pages/MePage/MeCardPage.tsx.
// Тексты — только заглушки (репо публичный). Где данных нет — NO_DATA (Л5 А). Балла Чек-Апа нет (Р-18).
// Дата регистрации — только дата, в поясе участника; tz пустой или не распознан → по UTC (Ш-3).
// Зоны — местные заглушки, /checkup/config не запрашивается (Ш-4).
import type { MeCard } from '../api/client.ts';

export const ME_TEXT = {
  cardTitle: 'Заглушка: моя карточка',
  toDay: 'Заглушка: к экрану дня',
  shortNo: 'Заглушка: номер участника',
  registered: 'Заглушка: дата регистрации',
  tz: 'Заглушка: часовой пояс',
  position: 'Заглушка: позиция',
  lives: 'Заглушка: жизни',
  weightStart: 'Заглушка: вес на старте',
  weightCurrent: 'Заглушка: вес сейчас',
  checkup: 'Заглушка: Чек-Ап',
  zoneStart: 'Заглушка: зона на старте',
  zoneLast: 'Заглушка: последняя зона',
  checkupDone: 'Заглушка: Чек-Ап пройден',
  checkupNotDone: 'Заглушка: Чек-Ап не пройден',
} as const;

export const NO_DATA = 'Заглушка: нет данных';

export const ZONE_TITLES = {
  green: 'Заглушка: зелёная зона',
  yellow: 'Заглушка: жёлтая зона',
  red: 'Заглушка: красная зона',
} as const;

function formatDate(ms: number, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('ru-RU', {
    timeZone,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).formatToParts(new Date(ms));
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  return `${part('day')}.${part('month')}.${part('year')}`;
}

/** Дата «ДД.ММ.ГГГГ» без времени в поясе tz; tz пустой или не распознан → UTC; битая строка → null. */
export function localDate(iso: unknown, tz: string | null | undefined): string | null {
  if (typeof iso !== 'string') return null;
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return null;
  if (typeof tz === 'string' && tz !== '') {
    try {
      return formatDate(ms, tz);
    } catch {
      // Пояс не распознан — ниже дата по UTC.
    }
  }
  return formatDate(ms, 'UTC');
}

/** green / yellow / red → заглушка зоны; иначе NO_DATA. */
export function zoneTitle(zone: unknown): string {
  if (zone === 'green' || zone === 'yellow' || zone === 'red') return ZONE_TITLES[zone];
  return NO_DATA;
}

/** Конечное число → «<число> кг»; иначе NO_DATA. */
export function weightText(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${String(v)} кг` : NO_DATA;
}

/** Три целых номера → «Заглушка: этап S, модуль M, день D»; иначе NO_DATA. */
export function positionText(p: unknown): string {
  if (typeof p !== 'object' || p === null) return NO_DATA;
  const o = p as Record<string, unknown>;
  const { stage_no: s, module_no: m, day_no: d } = o;
  if (!Number.isInteger(s) || !Number.isInteger(m) || !Number.isInteger(d)) return NO_DATA;
  return `Заглушка: этап ${String(s)}, модуль ${String(m)}, день ${String(d)}`;
}

export interface CardRow {
  label: string;
  value: string;
}

/** Ровно 10 строк карточки в фиксированном порядке; пустых значений нет (Л5). */
export function cardRows(card: MeCard): CardRow[] {
  const m = card.measurements;
  return [
    { label: ME_TEXT.shortNo, value: card.short_no },
    { label: ME_TEXT.registered, value: localDate(card.registered_at, card.tz) ?? NO_DATA },
    { label: ME_TEXT.tz, value: card.tz ?? NO_DATA },
    { label: ME_TEXT.position, value: positionText(card.position) },
    { label: ME_TEXT.lives, value: String(card.lives) },
    { label: ME_TEXT.weightStart, value: weightText(m.weight_start_kg) },
    { label: ME_TEXT.weightCurrent, value: weightText(m.weight_current_kg) },
    { label: ME_TEXT.checkup, value: m.checkup_completed ? ME_TEXT.checkupDone : ME_TEXT.checkupNotDone },
    { label: ME_TEXT.zoneStart, value: zoneTitle(m.zone_start) },
    { label: ME_TEXT.zoneLast, value: zoneTitle(m.zone_last) },
  ];
}

/** Ссылка на карточку с экрана дня: поле рефлексии пустое (после trim) и отчёт не отправляется (Ш-2). */
export function canOpenCard(reflection: string, sending: boolean): boolean {
  return reflection.trim() === '' && !sending;
}
