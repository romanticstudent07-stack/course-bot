// apps/miniapp/src/pages/MePage/MeChangeMapPage.tsx — экран me.change-map /me/change-map (miniapp-i3-2b §7.3).
//
// Только просмотр: 4 слоя (anthro, wellbeing, checkup, functional), старт и до 5 последних значений.
// Код самочувствия не выводится (Ш-5); балла Чек-Апа нет; слоя фото нет (Р-3).
// GET /me/change-map и GET /me/card (ради tz) параллельно; ошибка любого — ошибка экрана (Ш-3).
// «Повторить» — оба GET заново; автоповтора и таймеров нет (Ш-7).
// Ответы живут только в state React: не на устройство, не в лог, не в адрес.
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';

import { getMeCard, getMeChangeMap } from '../../api/client.ts';
import { dayErrorMessage } from '../../components/dayScreen.ts';
import { ME_TEXT, changeMapView, type ChangeMapLayerView } from '../../components/me.ts';

const pageStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 16, padding: 16 };
const layerStyle: CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4 };
const titleStyle: CSSProperties = { fontWeight: 600 };
const listStyle: CSSProperties = { margin: 0, paddingLeft: 20 };

type LoadStatus = 'loading' | 'ready' | 'error';

/** Вид без хуков и без ссылок: заголовок; по каждому слою — название, старт и последние значения. */
export function MeChangeMapView({ layers }: { layers: ChangeMapLayerView[] }) {
  return (
    <>
      <h1>{ME_TEXT.changeMapTitle}</h1>
      {layers.map((l) => (
        <div key={l.layer} style={layerStyle}>
          <span style={titleStyle}>{l.title}</span>
          <span>{`${ME_TEXT.baselineLabel}: ${l.baseline}`}</span>
          {l.recent.length > 0 && (
            <>
              <span>{ME_TEXT.recentLabel}</span>
              <ul style={listStyle}>
                {l.recent.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      ))}
    </>
  );
}

export function MeChangeMapPage() {
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [layers, setLayers] = useState<ChangeMapLayerView[]>([]);
  const [loadError, setLoadError] = useState<unknown>(null);

  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);

  const load = useCallback(() => {
    const id = ++requestIdRef.current;
    setStatus('loading');
    Promise.all([getMeChangeMap(), getMeCard()])
      .then(([map, card]) => {
        if (!mountedRef.current || id !== requestIdRef.current) return;
        setLayers(changeMapView(map, card.tz));
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
      <MeChangeMapView layers={layers}/>
      <Link to="/me">{ME_TEXT.toCard}</Link>
    </div>
  );
}
