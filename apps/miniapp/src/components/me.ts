// apps/miniapp/src/components/me.ts — чистые функции экрана me.card /me (miniapp-i3-2a §7.2).
//
// Без React и без запросов (тесты — vitest, environment node). Экран — pages/MePage/MeCardPage.tsx.
// Тексты — только заглушки (репо публичный). Где данных нет — NO_DATA (Л5 А). Балла Чек-Апа нет (Р-18).
// Дата регистрации — только дата, в поясе участника; tz пустой или не распознан → по UTC (Ш-3).
// Зоны — местные заглушки, /checkup/config не запрашивается (Ш-4).
import type { ChangeMapPoint, MeCard } from '../api/client.ts';

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
  consentsTitle: 'Заглушка: мои согласия',
  changeMapTitle: 'Заглушка: карта изменений',
  toCard: 'Заглушка: назад к карточке',
  consentActive: 'Заглушка: действует',
  wellbeingRecorded: 'Заглушка: ответ записан',
  baselineLabel: 'Заглушка: старт',
  recentLabel: 'Заглушка: последние',
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

// ---- Экраны me.consents и me.change-map (miniapp-i3-2b §7.2) ----
// Только просмотр: отзыва согласий нет (Л4 А). legal_status не показывается (Ш-6).
// Код самочувствия не выводится (Ш-5); балла Чек-Апа нет; слоя фото нет (Р-3).

export const LAYER_TITLES = {
  anthro: 'Заглушка: вес',
  wellbeing: 'Заглушка: самочувствие',
  checkup: 'Заглушка: Чек-Ап',
  functional: 'Заглушка: функциональные',
} as const;

type LayerId = keyof typeof LAYER_TITLES;

const LAYER_ORDER: readonly LayerId[] = ['anthro', 'wellbeing', 'checkup', 'functional'];

/** Дата «ДД.ММ.ГГГГ» в поясе tz (Ш-3); битая или пустая → NO_DATA. */
export function dateOrNoData(iso: unknown, tz: string | null | undefined): string {
  return localDate(iso, tz) ?? NO_DATA;
}

export interface ConsentRow {
  id: string;
  given: string;
  state: string;
}

/** Строки согласий по id по возрастанию (C0…C6); не массив → []; legal_status не попадает (Ш-6). */
export function consentRows(list: unknown, tz: string | null | undefined): ConsentRow[] {
  if (!Array.isArray(list)) return [];
  const items = list.filter(
    (x): x is Record<string, unknown> =>
      typeof x === 'object' && x !== null && typeof (x as Record<string, unknown>).id === 'string',
  );
  return items
    .map((c) => {
      const id = c.id as string;
      return {
        id,
        given: `Заглушка: ${id} — дано ${dateOrNoData(c.given_at, tz)}`,
        state:
          c.revoked_at === null || c.revoked_at === undefined
            ? ME_TEXT.consentActive
            : `Заглушка: отозвано ${dateOrNoData(c.revoked_at, tz)}`,
      };
    })
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

/** Одна точка слоя → строка; wellbeing — без значения (Ш-5); прочие слои → NO_DATA. */
export function pointLine(layer: string, point: ChangeMapPoint, tz: string | null | undefined): string {
  const date = dateOrNoData(point.at, tz);
  if (layer === 'anthro') return `${weightText(point.value)}, ${date}`;
  if (layer === 'checkup') return `${zoneTitle(point.value)}, ${date}`;
  if (layer === 'wellbeing') return `${ME_TEXT.wellbeingRecorded}, ${date}`;
  return NO_DATA;
}

export interface ChangeMapLayerView {
  layer: string;
  title: string;
  baseline: string;
  recent: string[];
}

function isPoint(p: unknown): p is ChangeMapPoint {
  return typeof p === 'object' && p !== null;
}

/** Ровно 4 слоя в порядке anthro, wellbeing, checkup, functional, даже при битом теле (Л5). */
export function changeMapView(map: unknown, tz: string | null | undefined): ChangeMapLayerView[] {
  const raw =
    typeof map === 'object' && map !== null ? (map as Record<string, unknown>).layers : undefined;
  const layers = Array.isArray(raw) ? raw : [];
  return LAYER_ORDER.map((id) => {
    const found = layers.find(
      (l): l is Record<string, unknown> =>
        typeof l === 'object' && l !== null && (l as Record<string, unknown>).layer === id,
    );
    const view: ChangeMapLayerView = { layer: id, title: LAYER_TITLES[id], baseline: NO_DATA, recent: [] };
    if (found === undefined || !isPoint(found.baseline)) return view;
    view.baseline = pointLine(id, found.baseline, tz);
    const recent = Array.isArray(found.recent) ? found.recent : [];
    view.recent = recent.filter(isPoint).map((p) => pointLine(id, p, tz));
    return view;
  });
}
