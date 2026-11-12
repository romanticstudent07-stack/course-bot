// apps/miniapp/src/components/me.test.ts — vitest, environment node, без DOM (miniapp-i3-2a §9).
// JSX здесь запрещён (файл .ts): рендер через createElement + renderToStaticMarkup.
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { MeCard } from '../api/client.ts';
import { MeCardView } from '../pages/MePage/MeCardPage.tsx';
import {
  ME_TEXT,
  NO_DATA,
  ZONE_TITLES,
  canOpenCard,
  cardRows,
  localDate,
  positionText,
  weightText,
  zoneTitle,
} from './me.ts';

const ISO = '2026-10-22T22:30:00Z';

const FULL: MeCard = {
  short_no: '#000123',
  registered_at: ISO,
  tz: 'Asia/Yekaterinburg',
  position: { stage_no: 1, module_no: 2, day_no: 3 },
  lives: 3,
  measurements: {
    weight_start_kg: 72.5,
    weight_current_kg: 70,
    checkup_completed: true,
    zone_start: 'yellow',
    zone_last: 'green',
  },
};

const FRESH: MeCard = {
  short_no: '#000124',
  registered_at: ISO,
  tz: null,
  position: null,
  lives: 3,
  measurements: {
    weight_start_kg: null,
    weight_current_kg: null,
    checkup_completed: false,
    zone_start: null,
    zone_last: null,
  },
};

describe('localDate', () => {
  it('1. дата в поясе участника', () => {
    expect(localDate(ISO, 'Asia/Yekaterinburg')).toBe('23.10.2026');
  });

  it('2. tz пустой или не распознан → UTC; битая строка → null', () => {
    expect(localDate(ISO, null)).toBe('22.10.2026');
    expect(localDate(ISO, undefined)).toBe('22.10.2026');
    expect(localDate(ISO, 'Плохо/Пояс')).toBe('22.10.2026');
    expect(localDate('плохо', 'Asia/Omsk')).toBeNull();
    expect(localDate(undefined, 'Asia/Omsk')).toBeNull();
    expect(localDate(42, 'Asia/Omsk')).toBeNull();
  });
});

describe('подписи значений', () => {
  it('3. zoneTitle', () => {
    const titles = [zoneTitle('green'), zoneTitle('yellow'), zoneTitle('red')];
    expect(titles).toEqual([ZONE_TITLES.green, ZONE_TITLES.yellow, ZONE_TITLES.red]);
    expect(new Set(titles).size).toBe(3);
    expect(zoneTitle('purple')).toBe(NO_DATA);
    expect(zoneTitle(null)).toBe(NO_DATA);
  });

  it('4. weightText', () => {
    expect(weightText(72.5)).toBe('72.5 кг');
    expect(weightText(null)).toBe(NO_DATA);
    expect(weightText(NaN)).toBe(NO_DATA);
    expect(weightText('72')).toBe(NO_DATA);
  });

  it('5. positionText', () => {
    const text = positionText({ stage_no: 1, module_no: 2, day_no: 3 });
    expect(text).not.toBe(NO_DATA);
    expect(text).toContain('1');
    expect(text).toContain('2');
    expect(text).toContain('3');
    expect(positionText(null)).toBe(NO_DATA);
    expect(positionText({ stage_no: 1, module_no: 2 })).toBe(NO_DATA);
  });
});

describe('cardRows', () => {
  it('6. полная карточка: 10 строк, значения — по функциям', () => {
    const rows = cardRows(FULL);
    expect(rows).toHaveLength(10);
    const values = rows.map((r) => r.value);
    expect(values).toEqual([
      '#000123',
      localDate(ISO, 'Asia/Yekaterinburg'),
      'Asia/Yekaterinburg',
      positionText(FULL.position),
      '3',
      weightText(72.5),
      weightText(70),
      ME_TEXT.checkupDone,
      zoneTitle('yellow'),
      zoneTitle('green'),
    ]);
    expect(values[1]).toBe('23.10.2026');
  });

  it('7. карточка сразу после first-launch: пустых нет, NO_DATA ровно в 6 строках', () => {
    const rows = cardRows(FRESH);
    expect(rows).toHaveLength(10);
    for (const r of rows) {
      expect(r.label.trim()).not.toBe('');
      expect(r.value.trim()).not.toBe('');
    }
    expect(rows.filter((r) => r.value === NO_DATA)).toHaveLength(6);
    expect(rows[7].value).toBe(ME_TEXT.checkupNotDone);
  });
});

describe('canOpenCard', () => {
  it('8. ссылка только при пустом поле и без отправки', () => {
    expect(canOpenCard('', false)).toBe(true);
    expect(canOpenCard('   ', false)).toBe(true);
    expect(canOpenCard('ab', false)).toBe(false);
    expect(canOpenCard('', true)).toBe(false);
  });
});

describe('MeCardView', () => {
  it('9. номер и заголовок; нет балла, ссылок и полей ввода', () => {
    const html = renderToStaticMarkup(createElement(MeCardView, { card: FULL }));
    expect(html).toContain('#000123');
    expect(html).toContain(ME_TEXT.cardTitle);
    expect(html.toLowerCase()).not.toContain('score');
    expect(html).not.toContain('<a ');
    expect(html).not.toContain('<input');
  });
});

describe('тексты', () => {
  it('10. все тексты — заглушки', () => {
    for (const v of [...Object.values(ME_TEXT), ...Object.values(ZONE_TITLES), NO_DATA]) {
      expect(v.startsWith('Заглушка: ')).toBe(true);
    }
  });
});
