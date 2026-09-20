// ClippyMe redesign — ViralPublishModal: concurrent publish for Viral Studio items.
// Reuses Zernio platforms mapping, LazyVideo, and localDatePlus from the redesign UI.
import { useState, useEffect, useRef } from 'react';
import { Icon, Social, Btn, Switch, PlatPill } from './primitives';
import { LazyVideo } from './LazyVideo';
import { getZernio } from './realApi';
import { publishViralItems, viralVideoSrc } from './viralApi';
import { PLAT } from './publish';
import { localDatePlus } from '../lib/scheduleDates';
import { useModalA11y } from './useModalA11y';

function ViralPubRow({ item, idx, st, plats }) {
  const status = typeof st === 'object' && st ? st.state : st;
  const errMsg = typeof st === 'object' && st ? st.error : null;
  const tasks = Object.keys(plats).filter((k) => plats[k]);
  const done = status === 'done';
  const error = status === 'error';
  const videoUrl = viralVideoSrc(item);

  return (
    <div className={'pubrow' + (done ? ' done' : '')}>
      <div className="pthumb" style={{ background: '#000', overflow: 'hidden' }}>
        <LazyVideo src={videoUrl} muted playsInline rootMargin="120px"
          style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </div>
      <div className="pinfo">
        <div className="pttl">{item.selected_headline || item.product_code || `Vídeo ${idx + 1}`}</div>
        <div className="pplats">
          {tasks.map((p) => (
            <div className="pp" key={p}>
              <Social n={PLAT[p].icon} color={done ? '02C5BF' : '7E7E8F'} size={13} />
              <div className="ptrack"><i className={p} style={{ width: done ? '100%' : status === 'uploading' ? '70%' : '0%', transition: 'width .4s' }}></i></div>
            </div>
          ))}
          <span className={'pstat' + (done ? ' done' : status === 'uploading' ? '' : ' wait')}
            style={error ? { color: 'var(--danger)' } : undefined}
            title={error && errMsg ? errMsg : undefined}>
            {error ? (errMsg ? `falha: ${errMsg.slice(0, 60)}` : 'falha') : done ? 'publicado' : status === 'uploading' ? 'enviando' : 'na fila'}
          </span>
        </div>
      </div>
      <div className="pcheck"><Icon n={done ? 'check' : error ? 'x' : 'loader'} /></div>
    </div>
  );
}

export function ViralPublishModal({ items = [], onClose, onPublished, pushToast }) {
  const all = items.length > 1;
  const [zernio, setZernio] = useState(null);
  const [plats, setPlats] = useState({ tiktok: true, ig: true, yt: false });
  const [schedule, setSchedule] = useState(true);
  const [stage, setStage] = useState('setup'); // setup | uploading | done
  const [progress, setProgress] = useState({});

  useEffect(() => {
    getZernio().then(setZernio).catch(() => setZernio({ configured: false }));
  }, []);

  const panelRef = useModalA11y(onClose);
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const accounts = zernio?.accounts || {};
  const toggle = (k) => setPlats((p) => ({ ...p, [k]: !p[k] }));

  const platTargets = () => Object.keys(plats)
    .filter((k) => plats[k] && accounts[PLAT[k].acct])
    .map((k) => ({ platform: PLAT[k].platform, accountId: accounts[PLAT[k].acct] }));

  const targets = platTargets();
  const ready = zernio?.configured && targets.length > 0;

  const handlePublish = async () => {
    if (!ready || stage !== 'setup') return;
    setStage('uploading');

    const initial = {};
    items.forEach((it) => { initial[it.id] = 'uploading'; });
    setProgress(initial);

    try {
      const scheduleMode = schedule ? 'auto' : 'now';
      const startDate = schedule ? localDatePlus(0) : undefined;
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

      const res = await publishViralItems({
        item_ids: items.map((it) => it.id),
        platforms: targets,
        schedule_mode: scheduleMode,
        timezone,
        start_date: startDate,
      });

      const nextProg = {};
      items.forEach((it) => { nextProg[it.id] = 'done'; });
      if (mountedRef.current) {
        setProgress(nextProg);
        setStage('done');
      }

      pushToast?.('success', `${items.length} vídeo(s) enviado(s) para publicação!`);
      onPublished?.(res);
      setTimeout(() => {
        if (mountedRef.current) onClose();
      }, 1200);
    } catch (err) {
      if (mountedRef.current) {
        const nextProg = {};
        items.forEach((it) => { nextProg[it.id] = { state: 'error', error: err.message }; });
        setProgress(nextProg);
        setStage('setup');
      }
      pushToast?.('error', `Erro na publicação: ${err.message}`);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal modal-pub" ref={panelRef} onClick={(e) => e.stopPropagation()}
        role="dialog" aria-modal="true" aria-labelledby="viral-pub-modal-title">
        <div className="mhead">
          <div className="mhead-txt">
            <h2 id="viral-pub-modal-title">{all ? `Publicar lote (${items.length} vídeos)` : 'Publicar vídeo'}</h2>
            <div className="msub">
              {stage === 'uploading' ? 'Publicando via Zernio…'
                : stage === 'done' ? 'Publicação concluída!'
                : 'Envie para suas redes sociais vinculadas'}
            </div>
          </div>
          <button type="button" className="mclose" onClick={onClose} aria-label="Fechar modal"><Icon n="x" /></button>
        </div>

        <div className="mbody">
          {stage === 'setup' && (
            <>
              <div className="pub-section">
                <div className="pub-lbl">Plataformas de destino</div>
                <div className="plat-pick">
                  {Object.keys(PLAT).map((k) => (
                    <PlatPill key={k} id={k} on={plats[k]} toggle={() => toggle(k)}
                      connected={!!accounts[PLAT[k].acct]} />
                  ))}
                </div>
                {!zernio?.configured && (
                  <div className="pub-warn">
                    <Icon n="triangle-alert" /> Zernio não está configurado. Conecte sua chave nas Configurações.
                  </div>
                )}
              </div>

              <div className="pub-section">
                <div className="pub-opt-row">
                  <div>
                    <div className="opt-title">Agendar postagens</div>
                    <div className="opt-desc">Distribui as postagens (1 vídeo por dia) para evitar bloqueio</div>
                  </div>
                  <Switch on={schedule} onChange={setSchedule} label="Agendar postagens" />
                </div>
              </div>
            </>
          )}

          <div className="pub-list" style={{ maxHeight: 280, overflowY: 'auto' }}>
            {items.map((item, idx) => (
              <ViralPubRow key={item.id} item={item} idx={idx} st={progress[item.id] || (stage === 'setup' ? 'queued' : 'uploading')} plats={plats} />
            ))}
          </div>
        </div>

        <div className="mfoot">
          <Btn variant="secondary" onClick={onClose} disabled={stage === 'uploading'}>Cancelar</Btn>
          <Btn variant="grad" onClick={handlePublish} disabled={!ready || stage !== 'setup'} loading={stage === 'uploading'}>
            {stage === 'uploading' ? 'Publicando…' : schedule ? 'Agendar publicação' : 'Publicar agora'}
          </Btn>
        </div>
      </div>
    </div>
  );
}
