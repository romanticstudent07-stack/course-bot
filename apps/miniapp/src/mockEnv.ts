// apps/miniapp/src/mockEnv.ts — мок окружения Telegram для локальной разработки в браузере.
// Взято из шаблона reactjs-template. Работает ТОЛЬКО при import.meta.env.DEV:
// в production-сборке блок вырезается, и вне Telegram показывается EnvUnsupported.
//
// ВНИМАНИЕ: hash ниже — фиктивный. Сервер с реальной валидацией initData (Итерация 1)
// такой запрос отклонит — это ожидаемо.
import { emitEvent, isTMA, mockTelegramEnv } from '@telegram-apps/sdk-react';

if (import.meta.env.DEV) {
  if (!(await isTMA('complete'))) {
    const themeParams = {
      accent_text_color: '#6ab2f2',
      bg_color: '#17212b',
      button_color: '#5288c1',
      button_text_color: '#ffffff',
      destructive_text_color: '#ec3942',
      header_bg_color: '#17212b',
      hint_color: '#708499',
      link_color: '#6ab3f3',
      secondary_bg_color: '#232e3c',
      section_bg_color: '#17212b',
      section_header_text_color: '#6ab3f3',
      subtitle_text_color: '#708499',
      text_color: '#f5f5f5',
    } as const;
    const noInsets = { left: 0, top: 0, bottom: 0, right: 0 } as const;

    mockTelegramEnv({
      onEvent(e) {
        if (e[0] === 'web_app_request_theme') {
          return emitEvent('theme_changed', { theme_params: themeParams });
        }
        if (e[0] === 'web_app_request_viewport') {
          return emitEvent('viewport_changed', {
            height: window.innerHeight,
            width: window.innerWidth,
            is_expanded: true,
            is_state_stable: true,
          });
        }
        if (e[0] === 'web_app_request_content_safe_area') {
          return emitEvent('content_safe_area_changed', noInsets);
        }
        if (e[0] === 'web_app_request_safe_area') {
          return emitEvent('safe_area_changed', noInsets);
        }
      },
      launchParams: new URLSearchParams([
        ['tgWebAppThemeParams', JSON.stringify(themeParams)],
        ['tgWebAppData', new URLSearchParams([
          ['auth_date', ((Date.now() / 1000) | 0).toString()],
          ['hash', 'dev-mock-hash'],
          ['signature', 'dev-mock-signature'],
          ['user', JSON.stringify({ id: 1, first_name: 'Dev' })],
        ]).toString()],
        ['tgWebAppVersion', '8.4'],
        ['tgWebAppPlatform', 'tdesktop'],
      ]),
    });

    console.info('[dev] Окружение Telegram замокано (только dev-режим Vite).');
  }
}
