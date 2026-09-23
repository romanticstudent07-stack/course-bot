// apps/miniapp/src/components/EnvUnsupported.tsx
// Заглушка, если Mini App открыт вне Telegram или в слишком старом клиенте.
// Текст временный — в Итерации 1 переедет в text_registry (И4, ключ {домен}.{имя}).
export function EnvUnsupported() {
  return (
    <div className="page">
      <h1>Откройте Mini App из Telegram</h1>
      <p className="hint">
        Установите последнюю версию Telegram и откройте приложение кнопкой меню бота.
      </p>
    </div>
  );
}
