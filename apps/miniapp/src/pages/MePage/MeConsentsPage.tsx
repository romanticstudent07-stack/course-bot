// apps/miniapp/src/pages/MePage/MeConsentsPage.tsx — экран me.consents /me/consents (miniapp-i3-2b §7.3).
//
// Только просмотр: кнопок отзыва нет (Л4 А, отзыв — И4); legal_status не показывается (Ш-6).
// GET /consents и GET /me/card (ради tz) параллельно; ошибка любого — ошибка экрана (Ш-3).
// «Повторить» — оба GET заново; автоповтора и таймеров нет (Ш-7).
// Ответы живут только в state React: не на устройство, не в лог, не в адрес.
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';

import { getConsents, getMeCard } from '../../api/client.ts';
import { dayErrorMessage } from '../../components/dayScreen.ts';
import { ME_TEXT, NO_DATA, consentRows, type ConsentRow } from '../../components/me.ts';

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };
const rowStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4 };
const labelStyle: CSSProperties = { fontWeight: 600 };

type LoadStatus = 'loading' | 'ready' | 'error';

/** Вид без хуков и без ссылок: заголовок; на каждое согласие две строки; пусто → NO_DATA. */
export function MeConsentsView({ rows }: { rows: ConsentRow[] }) {
  return (
    <>
      <h1>{ME_TEXT.consentsTitle}</h1>
      {rows.length === 0 ? (
        <p>{NO_DATA}</p>
      ) : (
        rows.map((row) => (
          <div key={row.id} style={rowStyle}>
            <span style={labelStyle}>{row.given}</span>
            <span>{row.state}</span>
          </div>
        ))
      )}
    </>
  );
}

export function MeConsentsPage() {
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [rows, setRows] = useState<ConsentRow[]>([]);
  const [loadError, setLoadError] = useState<unknown>(null);

  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);

  const load = useCallback(() => {
    const id = ++requestIdRef.current;
    setStatus('loading');
    Promise.all([getConsents(), getMeCard()])
      .then(([list, card]) => {
        if (!mountedRef.current || id !== requestIdRef.current) return;
        setRows(consentRows(list, card.tz));
        setLoadError(null);
        setStatus('ready');
      })
      .catch((err: unknown) => {
        if (!mountedRef.current || id !== requestIdRef.current) return;
        setLoadError(err);
        setStatus('error');
      });
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    load();
    return () => {
      mountedRef.current = false;
    };
  }, [load]);

  if (status === 'loading') {
    return (
      <div className="page" style={pageStyle}>
        <p>Загрузка…</p>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="page" style={pageStyle}>
        <p>{dayErrorMessage(loadError)}</p>
        <button type="button" onClick={load}>
          Повторить
        </button>
        <Link to="/me">{ME_TEXT.toCard}</Link>
      </div>
    );
  }

  return (
    <div className="page" style={pageStyle}>
      <MeConsentsView rows={rows}/>
      <Link to="/me">{ME_TEXT.toCard}</Link>
    </div>
  );
}
