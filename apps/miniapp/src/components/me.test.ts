// apps/miniapp/src/components/me.test.ts — vitest, environment node, без DOM (miniapp-i3-2a §9).
// JSX здесь запрещён (файл .ts): рендер через createElement + renderToStaticMarkup.
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { MeCard } from '../api/client.ts';
import { MeCardView } from '../pages/MePage/MeCardPage.tsx';
import { MeChangeMapView } from '../pages/MePage/MeChangeMapPage.tsx';
import { MeConsentsView } from '../pages/MePage/MeConsentsPage.tsx';
import {
  LAYER_TITLES,
  ME_TEXT,
  NO_DATA,
  ZONE_TITLES,
  canOpenCard,
  cardRows,
  changeMapView,
  consentRows,
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

// ---- miniapp-i3-2b §9: me.consents и me.change-map ----

const TZ = 'Asia/Yekaterinburg';
const LAYER_IDS = ['anthro', 'wellbeing', 'checkup', 'functional'];

function mapWith(layers: unknown[]): unknown {
  return { layers };
}

describe('consentRows', () => {
  it('11. действующее согласие: id и дата по tz, state — действует', () => {
    const rows = consentRows(
      [{ id: 'C1', given_at: ISO, revoked_at: null, legal_status: 'pre-legal-review' }],
      TZ,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].given).toContain('C1');
    expect(rows[0].given).toContain('23.10.2026');
    expect(rows[0].state).toBe(ME_TEXT.consentActive);
  });

  it('12. отозванное согласие: «отозвано» и дата отзыва; legal_status не попадает', () => {
    const rows = consentRows(
      [
        {
          id: 'C2',
          given_at: '2026-10-01T10:00:00Z',
          revoked_at: '2026-10-05T10:00:00Z',
          legal_status: 'pre-legal-review',
        },
      ],
      TZ,
    );
    expect(rows[0].state).toContain('отозвано');
    expect(rows[0].state).toContain('05.10.2026');
    expect(JSON.stringify(rows)).not.toContain('pre-legal-review');
  });

  it('13. не массив и пусто → []; порядок по id', () => {
    expect(consentRows(null, TZ)).toEqual([]);
    expect(consentRows({}, TZ)).toEqual([]);
    expect(consentRows([], TZ)).toEqual([]);
    const rows = consentRows(
      ['C2', 'C0', 'C1'].map((id) => ({ id, given_at: ISO, revoked_at: null, legal_status: 'x' })),
      TZ,
    );
    expect(rows.map((r) => r.id)).toEqual(['C0', 'C1', 'C2']);
  });
});

describe('changeMapView', () => {
  it('14. битое и пустое тело → 4 слоя по порядку, NO_DATA и []', () => {
    for (const map of [null, {}, { layers: [] }]) {
      const view = changeMapView(map, TZ);
      expect(view.map((l) => l.layer)).toEqual(LAYER_IDS);
      for (const l of view) {
        expect(l.baseline).toBe(NO_DATA);
        expect(l.recent).toEqual([]);
      }
    }
  });

  it('15. anthro: старт в кг с датой по tz; recent — 2 строки в порядке сервера', () => {
    const view = changeMapView(
      mapWith([
        {
          layer: 'anthro',
          metric: 'weight_kg',
          baseline: { value: 72.5, at: ISO },
          recent: [
            { value: 71, at: '2026-10-25T10:00:00Z' },
            { value: 70, at: '2026-10-28T10:00:00Z' },
          ],
        },
      ]),
      TZ,
    );
    const anthro = view[0];
    expect(anthro.baseline).toContain('кг');
    expect(anthro.baseline).toContain('23.10.2026');
    expect(anthro.recent).toHaveLength(2);
    expect(anthro.recent[0]).toContain('71');
    expect(anthro.recent[0]).toContain('25.10.2026');
    expect(anthro.recent[1]).toContain('70');
    expect(anthro.recent[1]).toContain('28.10.2026');
  });

  it('16. wellbeing: «ответ записан» и дата; кода нет', () => {
    const view = changeMapView(
      mapWith([{ layer: 'wellbeing', metric: 'wellbeing_code', baseline: { value: 'w3', at: ISO }, recent: [] }]),
      TZ,
    );
    expect(view[1].baseline).toContain(ME_TEXT.wellbeingRecorded);
    expect(view[1].baseline).toContain('23.10.2026');
    expect(JSON.stringify(view)).not.toContain('w3');
  });

  it('17. checkup: зона; functional без данных → NO_DATA', () => {
    const view = changeMapView(
      mapWith([
        { layer: 'checkup', metric: 'inflammation_zone', baseline: { value: 'green', at: ISO }, recent: [] },
        { layer: 'functional', metric: null, baseline: null, recent: [] },
      ]),
      TZ,
    );
    expect(view[2].baseline).toContain(ZONE_TITLES.green);
    expect(view[3].baseline).toBe(NO_DATA);
  });
});

describe('MeConsentsView и MeChangeMapView', () => {
  it('18. MeConsentsView: пусто → NO_DATA; строки C0 и C1; нет ссылок, кнопок и балла', () => {
    const empty = renderToStaticMarkup(createElement(MeConsentsView, { rows: [] }));
    expect(empty).toContain(NO_DATA);
    const rows = consentRows(
      ['C0', 'C1'].map((id) => ({ id, given_at: ISO, revoked_at: null, legal_status: 'x' })),
      TZ,
    );
    const html = renderToStaticMarkup(createElement(MeConsentsView, { rows }));
    expect(html).toContain('C0');
    expect(html).toContain('C1');
    for (const h of [empty, html]) {
      expect(h).not.toContain('<a ');
      expect(h).not.toContain('<button');
      expect(h.toLowerCase()).not.toContain('score');
    }
  });

  it('19. MeChangeMapView: 4 заголовка слоёв; нет кода, балла и ссылок', () => {
    const layers = changeMapView(
      mapWith([{ layer: 'wellbeing', metric: 'wellbeing_code', baseline: { value: 'w3', at: ISO }, recent: [] }]),
      TZ,
    );
    const html = renderToStaticMarkup(createElement(MeChangeMapView, { layers }));
    for (const title of Object.values(LAYER_TITLES)) {
      expect(html).toContain(title);
    }
    expect(html).not.toContain('w3');
    expect(html.toLowerCase()).not.toContain('score');
    expect(html).not.toContain('<a ');
  });

  it('20. все LAYER_TITLES — заглушки', () => {
    for (const v of Object.values(LAYER_TITLES)) {
      expect(v.startsWith('Заглушка: ')).toBe(true);
    }
  });
});
