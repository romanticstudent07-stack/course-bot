// apps/miniapp/src/init.ts — инициализация Telegram Mini Apps SDK.
// Упрощённая версия init.ts из шаблона reactjs-template:
//   - убран eruda (подгружает отладочную консоль; в prod не нужен);
//   - убран macOS-мок (добавим, если понадобится на реальных клиентах).
import {
  backButton,
  init as initSDK,
  initData,
  miniApp,
  setDebug,
  themeParams,
  viewport,
} from '@telegram-apps/sdk-react';

export function init(options: { debug: boolean }): void {
  setDebug(options.debug);
  initSDK();

  backButton.mount.ifAvailable();
  // initData.restore() — только для ОТРИСОВКИ (имя пользователя).
  // Для решений сервер валидирует сырую строку initData (AGENTS.md, запрет №7).
  initData.restore();

  if (miniApp.mountSync.isAvailable()) {
    themeParams.mountSync();
    miniApp.mountSync();
    themeParams.bindCssVars();
  }

  if (viewport.mount.isAvailable()) {
    void viewport.mount().then(() => {
      viewport.bindCssVars();
    });
  }
}
