// ClippyMe redesign — ViralEditModal: Staged review & edit surface for a single viral video.
// Visual structure matches EditClipModal:
// - Left: 9:16 vertical video preview.
// - Right: Clean tabs (Headlines · Legenda · Detalhes).
// Non-blocking: re-render & updates run cleanly in background.
import { useState } from 'react';
import { Icon, Btn } from './primitives';
import { useModalA11y } from './useModalA11y';
import { LazyVideo } from './LazyVideo';
import { viralVideoSrc } from './viralApi';

export function ViralEditModal({ item, brand, template, onClose, onSave, onReRender, onApprove, pushToast }) {
  const panelRef = useModalA11y(onClose);
  const isBusyOrFailed = ['PENDING', 'DOWNLOADING', 'ANALYZING', 'RENDERING', 'FAILED'].includes(item.status);
  const [tab, setTab] = useState(isBusyOrFailed ? 'logs' : 'headlines'); // 'headlines' | 'caption' | 'details' | 'logs'

  const [selectedHeadline, setSelectedHeadline] = useState(item.selected_headline || '');
  const [customHeadline, setCustomHeadline] = useState(item.selected_headline || '');
  const [caption, setCaption] = useState(item.caption || '');
  const [productCode, setProductCode] = useState(item.product_code || '');
  const [productUrl, setProductUrl] = useState(item.product_url || '');

  const [reRendering, setReRendering] = useState(false);
  const [saving, setSaving] = useState(false);

  const videoUrl = viralVideoSrc(item);
  const headlinesList = item.ai_copy?.headlines || [];

  const handleApplyHeadline = (h) => {
    setSelectedHeadline(h);
    setCustomHeadline(h);
  };

  const handleTriggerReRender = async () => {
    if (!customHeadline.trim()) {
      pushToast?.('warn', 'Informe uma headline para o vídeo.');
      return;
    }
    setReRendering(true);
    try {
      await onReRender?.(item, customHeadline.trim());
      setSelectedHeadline(customHeadline.trim());
      pushToast?.('success', 'Re-renderização iniciada em segundo plano!');
    } catch (err) {
      pushToast?.('error', `Erro ao re-renderizar: ${err.message}`);
    } finally {
      setReRendering(false);
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      await onSave?.(item.id, {
        selected_headline: customHeadline.trim() || undefined,
        caption: caption || undefined,
        product_code: productCode.trim() || undefined,
        product_url: productUrl.trim() || undefined,
      });
      pushToast?.('success', 'Alterações salvas!');
      onClose();
    } catch (err) {
      pushToast?.('error', `Erro ao salvar: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="overlay" onClick={onClose} role="presentation">
      <div
        className="modal wide"
        ref={panelRef}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="viral-edit-title"
        style={{ maxWidth: 840 }}
      >
        <div className="modal-head">
          <Icon n="sliders-horizontal" />
          <div>
            <h3 id="viral-edit-title">Revisar & Editar Vídeo</h3>
            <div className="mh-sub">
              {brand ? `${brand.name} (${brand.handle})` : 'Vídeo Comercial'} · {template?.name || 'Template'} · #{item.product_code || item.id.slice(0, 6)}
            </div>
          </div>
          <button type="button" className="x" onClick={onClose} aria-label="Fechar modal">
            <Icon n="x" />
          </button>
        </div>

        <div className="modal-body" style={{ padding: '18px 24px' }}>
          <div className="edit-grid" style={{ gridTemplateColumns: '260px 1fr', gap: 24 }}>
            {/* Left: 9:16 Video Preview */}
            <div>
              <div style={{ aspectRatio: '9/16', background: '#000', borderRadius: 'var(--r-md)', overflow: 'hidden', border: '1px solid var(--line-1)', position: 'relative' }}>
                {item.rendered_path ? (
                  <video
                    src={videoUrl}
                    controls
                    playsInline
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', padding: 20, textAlign: 'center', color: 'var(--fg-3)' }}>
                    <Icon n="loader" style={{ width: 28, height: 28, marginBottom: 10 }} />
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-2)' }}>Processando vídeo…</span>
                  </div>
                )}
              </div>
              <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <Btn
                  variant="secondary"
                  size="sm"
                  block
                  icon={reRendering ? 'loader' : 'refresh-cw'}
                  loading={reRendering}
                  onClick={handleTriggerReRender}
                >
                  Re-renderizar vídeo
                </Btn>
              </div>
            </div>

            {/* Right: Tabbed Controls */}
            <div>
              {item.error_message && (
                <div style={{ background: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 'var(--r-sm)', padding: '10px 14px', marginBottom: 14, color: '#fca5a5', fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                  <Icon n="alert-triangle" style={{ flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <strong style={{ display: 'block', color: '#fecaca', marginBottom: 2 }}>Falha no processamento:</strong>
                    <span>{item.error_message}</span>
                  </div>
                </div>
              )}
              <div className="edit-tabs">
                <button
                  type="button"
                  className={`tab${tab === 'headlines' ? ' active' : ''}`}
                  onClick={() => setTab('headlines')}
                >
                  <Icon n="sparkles" /><span className="lbl">Headlines da IA</span>
                </button>
                <button
                  type="button"
                  className={`tab${tab === 'caption' ? ' active' : ''}`}
                  onClick={() => setTab('caption')}
                >
                  <Icon n="align-left" /><span className="lbl">Legenda Comercial</span>
                </button>
                <button
                  type="button"
                  className={`tab${tab === 'details' ? ' active' : ''}`}
                  onClick={() => setTab('details')}
                >
                  <Icon n="tag" /><span className="lbl">Produto & Link</span>
                </button>
                <button
                  type="button"
                  className={`tab${tab === 'logs' ? ' active' : ''}`}
                  onClick={() => setTab('logs')}
                >
                  <Icon n="terminal" /><span className="lbl">Logs & Atividade</span>
                </button>
              </div>

              {/* TAB 1: HEADLINES */}
              {tab === 'headlines' && (
                <div>
                  {/* Multi-Signal Context Badges */}
                  {item.ai_context_summary && (
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                      <span style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', padding: '3px 8px', borderRadius: 'var(--r-sm)', fontSize: 'var(--text-3xs)', color: 'var(--fg-2)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        🎬 {item.ai_context_summary.scenes_count || 1} cenas ({item.ai_context_summary.keyframes_count || 0} frames)
                      </span>
                      <span style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', padding: '3px 8px', borderRadius: 'var(--r-sm)', fontSize: 'var(--text-3xs)', color: 'var(--fg-2)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        {item.ai_context_summary.has_audio ? '🎙️ Áudio com fala' : '🎵 Sem fala / Música'}
                      </span>
                      {item.ai_context_summary.has_original_caption && (
                        <span style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', padding: '3px 8px', borderRadius: 'var(--r-sm)', fontSize: 'var(--text-3xs)', color: 'var(--fg-2)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          📝 Post original capturado
                        </span>
                      )}
                      {item.ai_context_summary.duration > 0 && (
                        <span style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', padding: '3px 8px', borderRadius: 'var(--r-sm)', fontSize: 'var(--text-3xs)', color: 'var(--fg-3)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                          ⏱️ {item.ai_context_summary.duration}s
                        </span>
                      )}
                    </div>
                  )}

                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)', marginBottom: 12 }}>
                    Escolha uma das 5 opções magnéticas geradas pela IA ou personalize abaixo:
                  </div>

                  {headlinesList.length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                      {headlinesList.map((h, i) => {
                        const isSelected = selectedHeadline === h;
                        return (
                          <div
                            key={i}
                            role="button"
                            tabIndex={0}
                            onClick={() => handleApplyHeadline(h)}
                            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleApplyHeadline(h); }}
                            style={{
                              padding: '10px 14px',
                              borderRadius: 'var(--r-sm)',
                              background: isSelected ? 'rgba(10,129,217,.12)' : 'var(--bg-2)',
                              border: `1px solid ${isSelected ? 'var(--brand-blue)' : 'var(--line-1)'}`,
                              color: isSelected ? 'var(--fg-1)' : 'var(--fg-2)',
                              fontSize: 'var(--text-sm)',
                              fontWeight: isSelected ? 600 : 400,
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              transition: 'border-color .15s, background .15s',
                            }}
                          >
                            <span>{h}</span>
                            {isSelected && <Icon n="check" style={{ color: 'var(--brand-blue)', width: 16, height: 16, flexShrink: 0 }} />}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div style={{ padding: 20, textAlign: 'center', color: 'var(--fg-3)', fontSize: 'var(--text-xs)' }}>
                      Nenhuma sugestão da IA disponível para este item.
                    </div>
                  )}

                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', textTransform: 'uppercase', marginBottom: 6, fontWeight: 600 }}>
                      Headline Ativa no Vídeo
                    </label>
                    <input
                      type="text"
                      className="key-input"
                      style={{ width: '100%', height: 40 }}
                      value={customHeadline}
                      onChange={(e) => setCustomHeadline(e.target.value)}
                      placeholder="Digite a headline que aparecerá no topo do vídeo"
                    />
                    <div style={{ fontSize: 'var(--text-3xs)', color: 'var(--fg-3)', marginTop: 6 }}>
                      Ao alterar a headline, clique em <strong>Re-renderizar vídeo</strong> para gerar o novo MP4 com o template visual.
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: CAPTION */}
              {tab === 'caption' && (
                <div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)', marginBottom: 12 }}>
                    Legenda comercial completa sugerida pela IA para engajar e converter em vendas:
                  </div>
                  <textarea
                    rows={8}
                    className="key-input"
                    style={{ width: '100%', height: 'auto', padding: 12, lineHeight: 1.5, resize: 'vertical' }}
                    value={caption}
                    onChange={(e) => setCaption(e.target.value)}
                    placeholder="Escreva a legenda com gancho, código e hashtags..."
                  />
                  {brand?.default_cta && (
                    <div style={{ marginTop: 10, fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>
                      <strong>CTA padrão da marca:</strong> {brand.default_cta}
                    </div>
                  )}
                </div>
              )}

              {/* TAB 3: DETAILS */}
              {tab === 'details' && (
                <div>
                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', textTransform: 'uppercase', marginBottom: 6, fontWeight: 600 }}>
                      Código do Produto
                    </label>
                    <input
                      type="text"
                      className="key-input"
                      style={{ width: '100%', height: 40 }}
                      value={productCode}
                      onChange={(e) => setProductCode(e.target.value)}
                      placeholder="Ex: 2567"
                    />
                    <div style={{ fontSize: 'var(--text-3xs)', color: 'var(--fg-3)', marginTop: 4 }}>
                      Identificador informado aos seguidores para encontrar o item na sua bio ou catálogo.
                    </div>
                  </div>

                  <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', textTransform: 'uppercase', marginBottom: 6, fontWeight: 600 }}>
                      Link Individual de Afiliado (Opcional)
                    </label>
                    <input
                      type="url"
                      className="key-input"
                      style={{ width: '100%', height: 40 }}
                      value={productUrl}
                      onChange={(e) => setProductUrl(e.target.value)}
                      placeholder={brand?.default_affiliate_url || 'https://shopee.com.br/...'}
                    />
                    <div style={{ fontSize: 'var(--text-3xs)', color: 'var(--fg-3)', marginTop: 4 }}>
                      Se vazio, utiliza o link padrão configurado na marca ({brand?.default_affiliate_url || 'link da bio'}).
                    </div>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', textTransform: 'uppercase', marginBottom: 6, fontWeight: 600 }}>
                      URL de Origem
                    </label>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)', wordBreak: 'break-all', background: 'var(--bg-2)', padding: '8px 12px', borderRadius: 'var(--r-sm)' }}>
                      {item.source_url}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 4: LOGS & ATIVIDADE */}
              {tab === 'logs' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>
                    Histórico cronológico de telemetria e atividades de processamento do vídeo:
                  </div>
                  <div
                    style={{
                      background: '#090d13',
                      border: '1px solid var(--line-1)',
                      borderRadius: 'var(--r-sm)',
                      padding: '12px 14px',
                      fontFamily: 'var(--font-mono, monospace)',
                      fontSize: 'var(--text-2xs)',
                      maxHeight: 280,
                      overflowY: 'auto',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                    }}
                  >
                    {item.logs && item.logs.length > 0 ? (
                      item.logs.map((log, idx) => {
                        const isError = log.level === 'error' || log.stage === 'ERROR';
                        const isWarn = log.level === 'warn';
                        const isSuccess = log.stage === 'COMPLETE' || log.stage === 'PUBLISHED' || log.stage === 'APPROVE' || log.stage === 'RENDER_COMPLETE';
                        const stageColor = isError ? 'var(--brand-danger, #f87171)' : isWarn ? 'var(--brand-amber, #fbbf24)' : isSuccess ? 'var(--brand-teal, #34d399)' : 'var(--blue-400, #60a5fa)';
                        const timeStr = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '--:--:--';

                        return (
                          <div key={idx} style={{ lineHeight: 1.4, wordBreak: 'break-word' }}>
                            <span style={{ color: 'var(--fg-3)', marginRight: 8 }}>[{timeStr}]</span>
                            <span style={{ color: stageColor, fontWeight: 600, marginRight: 8 }}>[{log.stage || 'INFO'}]</span>
                            <span style={{ color: isError ? 'var(--brand-danger, #f87171)' : 'var(--fg-1)' }}>{log.message}</span>
                            {log.details && (
                              <div style={{ paddingLeft: 16, color: 'var(--fg-3)', fontSize: 'var(--text-3xs)', marginTop: 2 }}>
                                {typeof log.details === 'object' ? JSON.stringify(log.details) : String(log.details)}
                              </div>
                            )}
                          </div>
                        );
                      })
                    ) : (
                      <div style={{ color: 'var(--fg-3)', textAlign: 'center', padding: '24px 0' }}>
                        Nenhum log registrado para este item.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="modal-foot">
          {item.status === 'READY_FOR_REVIEW' && (
            <Btn
              variant="grad"
              icon="check"
              onClick={() => {
                onApprove?.(item);
                onClose();
              }}
            >
              Aprovar Vídeo
            </Btn>
          )}
          <div className="mf-right">
            <Btn variant="secondary" onClick={onClose}>
              Cancelar
            </Btn>
            <Btn variant="primary" loading={saving} onClick={handleSaveAll}>
              Salvar Alterações
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}
