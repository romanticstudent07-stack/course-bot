// apps/miniapp/src/pages/MePage/MeCardPage.tsx — экран me.card /me (miniapp-i3-2a §7.3).
//
// Один GET /miniapp/v1/me/card при монтировании и по «Повторить»; автоповтора и таймеров нет (Ш-7).
// Ответ живёт только в state React: не на устройство, не в лог, не в адрес. Балла Чек-Апа нет.
// Ссылка «к экрану дня» — в готовом виде и на экране ошибки; на «Загрузка…» её нет.
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';

import { getMeCard, type MeCard } from '../../api/client.ts';
import { dayErrorMessage } from '../../components/dayScreen.ts';
import { ME_TEXT, cardRows } from '../../components/me.ts';

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };
const rowStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4 };
const labelStyle: CSSProperties = { fontWeight: 600 };

type LoadStatus = 'loading' | 'ready' | 'error';

/** Вид карточки без хуков и без ссылок: заголовок и 10 строк «подпись — значение». */
export function MeCardView({ card }: { card: MeCard }) {
  return (
    <>
      <h1>{ME_TEXT.cardTitle}</h1>
      {cardRows(card).map((row) => (
        <div key={row.label} style={rowStyle}>
          <span style={labelStyle}>{row.label}</span>
          <span>{row.value}</span>
        </div>
      ))}
    </>
  );
}

export function MeCardPage() {
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [card, setCard] = useState<MeCard | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);

  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);

  const load = useCallback(() => {
    const id = ++requestIdRef.current;
    setStatus('loading');
    getMeCard()
      .then((resp: MeCard) => {
        if (!mountedRef.current || id !== requestIdRef.current) return;
        setCard(resp);
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

  if (status === 'error' || card === null) {
    return (
      <div className="page" style={pageStyle}>
        <p>{dayErrorMessage(loadError)}</p>
        <button type="button" onClick={load}>
          Повторить
        </button>
        <Link to="/day">{ME_TEXT.toDay}</Link>
      </div>
    );
  }

  return (
    <div className="page" style={pageStyle}>
      <MeCardView card={card}/>
      <Link to="/day">{ME_TEXT.toDay}</Link>
    </div>
  );
}
