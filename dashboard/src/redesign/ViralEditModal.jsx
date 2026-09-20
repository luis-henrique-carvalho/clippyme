// ClippyMe redesign — ViralEditModal: Staged review & edit surface for a single viral video.
// Visual structure matches EditClipModal:
// - Left: 9:16 vertical video preview.
// - Right: Clean tabs (Headlines · Legenda · Detalhes · Observabilidade & IA).
// Observability Hub: Sinais Extraídos (Keyframes gallery + Transcription + Original Metadata), Telemetria da LLM (Metrics, Prompt, Raw Response), Linha do Tempo (Terminal Logs).
import { useState } from 'react';
import { Icon, Btn } from './primitives';
import { useModalA11y } from './useModalA11y';
import { viralVideoSrc } from './viralApi';

export function ViralEditModal({ item, brand, template, onClose, onSave, onReRender, onApprove, pushToast }) {
  const [zoomedKeyframe, setZoomedKeyframe] = useState(null); // URL string of zoomed keyframe
  const handleModalClose = () => {
    if (zoomedKeyframe) {
      setZoomedKeyframe(null);
    } else {
      onClose?.();
    }
  };
  const panelRef = useModalA11y(handleModalClose);
  const isBusyOrFailed = ['PENDING', 'DOWNLOADING', 'ANALYZING', 'RENDERING', 'FAILED'].includes(item.status);
  const [tab, setTab] = useState(isBusyOrFailed ? 'observability' : 'headlines'); // 'headlines' | 'caption' | 'details' | 'observability' | 'logs'
  const [obsSubTab, setObsSubTab] = useState('signals'); // 'signals' | 'telemetry' | 'timeline'
  const [copiedKey, setCopiedKey] = useState(null);

  const [selectedHeadline, setSelectedHeadline] = useState(item.selected_headline || '');
  const [customHeadline, setCustomHeadline] = useState(item.selected_headline || '');
  const [caption, setCaption] = useState(item.caption || '');
  const [productCode, setProductCode] = useState(item.product_code || '');
  const [productUrl, setProductUrl] = useState(item.product_url || '');

  const [reRendering, setReRendering] = useState(false);
  const [saving, setSaving] = useState(false);

  const videoUrl = viralVideoSrc(item);
  const headlinesList = item.ai_copy?.headlines || [];

  // Multi-Signal context resolution
  const keyframeUrls = (item.keyframe_urls && item.keyframe_urls.length > 0)
    ? item.keyframe_urls
    : (item.ai_context_summary?.keyframe_urls || []);
  const transcript = item.ai_context_summary?.transcript || '';
  const transcriptWords = item.ai_context_summary?.transcript_words || (transcript ? transcript.split(/\s+/).filter(Boolean).length : 0);
  const hasSpeech = Boolean(transcript && transcript.trim());
  const originalTitle = item.source_metadata?.title || item.ai_context_summary?.title || '';
  const originalCaption = item.source_metadata?.description || item.source_metadata?.caption || item.ai_context_summary?.original_caption || '';
  const rawTags = item.source_metadata?.tags || item.ai_context_summary?.tags || [];
  const originalTags = Array.isArray(rawTags) ? rawTags : (typeof rawTags === 'string' ? rawTags.split(/\s+/).filter(Boolean) : []);
  const originalUploader = item.source_metadata?.uploader || item.ai_context_summary?.uploader || item.source_metadata?.channel || item.source_metadata?.creator || '';
  const viewCount = item.source_metadata?.view_count ?? item.ai_context_summary?.view_count ?? null;
  const likeCount = item.source_metadata?.like_count ?? item.ai_context_summary?.like_count ?? null;
  const commentCount = item.source_metadata?.comment_count ?? item.ai_context_summary?.comment_count ?? null;
  const repostCount = item.source_metadata?.repost_count ?? item.ai_context_summary?.repost_count ?? null;

  const formatCompactNumber = (num) => {
    if (num == null || isNaN(num)) return null;
    const n = Number(num);
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
    return n.toLocaleString('pt-BR');
  };

  // AI Telemetry resolution
  const aiTelemetry = item.ai_telemetry || {};
  const modelUsed = aiTelemetry.model || aiTelemetry.model_used || 'gemini-2.5-flash';
  const promptTokens = Number(aiTelemetry.prompt_tokens || 0);
  const candidateTokens = Number(aiTelemetry.candidate_tokens || 0);
  const totalTokens = Number(aiTelemetry.total_tokens || (promptTokens + candidateTokens));
  const estimatedCost = Number(aiTelemetry.estimated_cost_usd ?? aiTelemetry.cost_usd ?? 0);
  const latencyMs = Number(aiTelemetry.latency_ms || 0);
  const fullPrompt = typeof aiTelemetry.prompt === 'string'
    ? aiTelemetry.prompt
    : (aiTelemetry.prompt ? JSON.stringify(aiTelemetry.prompt, null, 2) : '');
  const rawResponse = typeof aiTelemetry.raw_response === 'string'
    ? aiTelemetry.raw_response
    : (aiTelemetry.raw_response
      ? JSON.stringify(aiTelemetry.raw_response, null, 2)
      : (item.ai_copy ? JSON.stringify(item.ai_copy, null, 2) : ''));

  const handleApplyHeadline = (h) => {
    setSelectedHeadline(h);
    setCustomHeadline(h);
  };

  const handleCopyText = (text, key, successMsg) => {
    if (!text) return;
    navigator.clipboard.writeText(text)
      .then(() => {
        setCopiedKey(key);
        setTimeout(() => setCopiedKey((curr) => curr === key ? null : curr), 2500);
        pushToast?.('success', successMsg || 'Texto copiado!');
      })
      .catch(() => {
        pushToast?.('warn', 'Não foi possível copiar o texto.');
      });
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

  const isObsTab = tab === 'observability' || tab === 'logs';

  return (
    <div className="overlay" onClick={onClose} role="presentation">
      <div
        className="modal wide"
        ref={panelRef}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="viral-edit-title"
        style={{ maxWidth: 880 }}
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
                  className={`tab${isObsTab ? ' active' : ''}`}
                  onClick={() => setTab('observability')}
                >
                  <Icon n="activity" /><span className="lbl">Observabilidade & IA</span>
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

              {/* TAB 4: OBSERVABILIDADE & IA (HUB COM 3 SUB-TABS) */}
              {isObsTab && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {/* Observability Sub-tabs Switcher */}
                  <div
                    style={{
                      display: 'flex',
                      gap: 4,
                      background: 'var(--bg-2)',
                      padding: 4,
                      borderRadius: 'var(--r-md)',
                      border: '1px solid var(--line-1)',
                    }}
                    role="tablist"
                    aria-label="Subseções de Observabilidade"
                  >
                    <button
                      type="button"
                      role="tab"
                      aria-selected={obsSubTab === 'signals'}
                      onClick={() => setObsSubTab('signals')}
                      style={{
                        flex: 1,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 6,
                        padding: '6px 10px',
                        borderRadius: 'var(--r-sm)',
                        fontSize: 'var(--text-xs)',
                        fontWeight: obsSubTab === 'signals' ? 600 : 500,
                        color: obsSubTab === 'signals' ? 'var(--fg-1)' : 'var(--fg-3)',
                        background: obsSubTab === 'signals' ? 'var(--bg-1)' : 'transparent',
                        border: obsSubTab === 'signals' ? '1px solid var(--line-1)' : '1px solid transparent',
                        cursor: 'pointer',
                        transition: 'all .15s ease',
                      }}
                    >
                      <Icon n="sparkles" style={{ width: 14, height: 14, color: 'var(--brand-teal, #34d399)' }} />
                      <span>Sinais Extraídos</span>
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={obsSubTab === 'telemetry'}
                      onClick={() => setObsSubTab('telemetry')}
                      style={{
                        flex: 1,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 6,
                        padding: '6px 10px',
                        borderRadius: 'var(--r-sm)',
                        fontSize: 'var(--text-xs)',
                        fontWeight: obsSubTab === 'telemetry' ? 600 : 500,
                        color: obsSubTab === 'telemetry' ? 'var(--fg-1)' : 'var(--fg-3)',
                        background: obsSubTab === 'telemetry' ? 'var(--bg-1)' : 'transparent',
                        border: obsSubTab === 'telemetry' ? '1px solid var(--line-1)' : '1px solid transparent',
                        cursor: 'pointer',
                        transition: 'all .15s ease',
                      }}
                    >
                      <Icon n="activity" style={{ width: 14, height: 14, color: 'var(--blue-400, #60a5fa)' }} />
                      <span>Telemetria da LLM</span>
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={obsSubTab === 'timeline'}
                      onClick={() => setObsSubTab('timeline')}
                      style={{
                        flex: 1,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 6,
                        padding: '6px 10px',
                        borderRadius: 'var(--r-sm)',
                        fontSize: 'var(--text-xs)',
                        fontWeight: obsSubTab === 'timeline' ? 600 : 500,
                        color: obsSubTab === 'timeline' ? 'var(--fg-1)' : 'var(--fg-3)',
                        background: obsSubTab === 'timeline' ? 'var(--bg-1)' : 'transparent',
                        border: obsSubTab === 'timeline' ? '1px solid var(--line-1)' : '1px solid transparent',
                        cursor: 'pointer',
                        transition: 'all .15s ease',
                      }}
                    >
                      <Icon n="terminal" style={{ width: 14, height: 14, color: 'var(--brand-amber, #fbbf24)' }} />
                      <span>Linha do Tempo</span>
                    </button>
                  </div>

                  {/* SUB-TAB 1: SINAIS EXTRAÍDOS */}
                  {obsSubTab === 'signals' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                      {/* Section 1: Keyframe Images Gallery */}
                      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-md)', padding: '12px 14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--fg-1)', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                            <Icon n="film" style={{ width: 14, height: 14, color: 'var(--brand-blue)' }} />
                            Frames Extraídos por Cena ({keyframeUrls.length} frames)
                          </span>
                          <span style={{ fontSize: 'var(--text-3xs)', color: 'var(--fg-3)' }}>
                            Clique para ampliar
                          </span>
                        </div>

                        {keyframeUrls.length > 0 ? (
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(105px, 1fr))', gap: 10 }}>
                            {keyframeUrls.map((url, idx) => (
                              <div
                                key={idx}
                                role="button"
                                tabIndex={0}
                                onClick={() => setZoomedKeyframe(url)}
                                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setZoomedKeyframe(url); }}
                                title={`Cena ${idx + 1} - Clique para zoom`}
                                style={{
                                  position: 'relative',
                                  aspectRatio: '9/16',
                                  borderRadius: 'var(--r-sm)',
                                  overflow: 'hidden',
                                  background: '#000',
                                  border: '1px solid var(--line-1)',
                                  cursor: 'pointer',
                                  transition: 'transform .15s ease, border-color .15s ease',
                                }}
                              >
                                <img
                                  src={url}
                                  alt={`Frame da Cena ${idx + 1}`}
                                  loading="lazy"
                                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                />
                                <div style={{ position: 'absolute', bottom: 4, left: 4, background: 'rgba(0,0,0,0.75)', color: '#fff', padding: '2px 6px', borderRadius: 4, fontSize: 'var(--text-3xs)', fontWeight: 600 }}>
                                  Cena {idx + 1}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div style={{ padding: '16px 0', textAlign: 'center', color: 'var(--fg-3)', fontSize: 'var(--text-2xs)' }}>
                            Nenhum frame extraído ou extração de cena pendente.
                          </div>
                        )}
                      </div>

                      {/* Section 2: Audio Transcription */}
                      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-md)', padding: '12px 14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--fg-1)' }}>
                              Transcrição de Áudio
                            </span>
                            {hasSpeech ? (
                              <span style={{ background: 'rgba(52, 211, 153, 0.12)', border: '1px solid rgba(52, 211, 153, 0.3)', color: 'var(--brand-teal, #34d399)', padding: '1px 6px', borderRadius: 'var(--r-xs)', fontSize: 'var(--text-3xs)', fontWeight: 600 }}>
                                🎙️ Fala detectada ({transcriptWords} palavras)
                              </span>
                            ) : (
                              <span style={{ background: 'rgba(251, 191, 36, 0.12)', border: '1px solid rgba(251, 191, 36, 0.3)', color: 'var(--brand-amber, #fbbf24)', padding: '1px 6px', borderRadius: 'var(--r-xs)', fontSize: 'var(--text-3xs)', fontWeight: 600 }}>
                                🎵 Instrumental / Sem fala
                              </span>
                            )}
                          </div>
                          {hasSpeech && (
                            <Btn
                              variant="secondary"
                              size="xs"
                              icon={copiedKey === 'transcript' ? 'check' : 'copy'}
                              onClick={() => handleCopyText(transcript, 'transcript', 'Transcrição copiada')}
                            >
                              {copiedKey === 'transcript' ? 'Copiado!' : 'Copiar'}
                            </Btn>
                          )}
                        </div>

                        {hasSpeech ? (
                          <div
                            style={{
                              background: 'var(--bg-1)',
                              border: '1px solid var(--line-1)',
                              borderRadius: 'var(--r-sm)',
                              padding: '10px 12px',
                              fontSize: 'var(--text-xs)',
                              color: 'var(--fg-2)',
                              lineHeight: 1.5,
                              maxHeight: 100,
                              overflowY: 'auto',
                            }}
                          >
                            {transcript}
                          </div>
                        ) : (
                          <div style={{ fontSize: 'var(--text-2xs)', color: 'var(--fg-3)', fontStyle: 'italic' }}>
                            Nenhuma faixa de voz identificada no áudio (conteúdo com trilha sonora ou ruído ambiente).
                          </div>
                        )}
                      </div>

                      {/* Section 3: Original Post Metadata */}
                      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-md)', padding: '12px 14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--fg-1)' }}>
                            Metadados do Post Original
                          </span>
                          {originalCaption && (
                            <Btn
                              variant="secondary"
                              size="xs"
                              icon={copiedKey === 'orig_caption' ? 'check' : 'copy'}
                              onClick={() => handleCopyText(originalCaption, 'orig_caption', 'Legenda original copiada')}
                            >
                              {copiedKey === 'orig_caption' ? 'Copiado!' : 'Copiar Legenda'}
                            </Btn>
                          )}
                        </div>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 'var(--text-2xs)' }}>
                          {originalTitle && (
                            <div>
                              <strong style={{ color: 'var(--fg-3)' }}>Título: </strong>
                              <span style={{ color: 'var(--fg-1)' }}>{originalTitle}</span>
                            </div>
                          )}
                          {originalUploader && (
                            <div>
                              <strong style={{ color: 'var(--fg-3)' }}>Autor / Canal: </strong>
                              <span style={{ color: 'var(--blue-400, #60a5fa)' }}>{originalUploader}</span>
                            </div>
                          )}
                          {(viewCount != null || likeCount != null || commentCount != null || repostCount != null) && (
                            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 2, marginBottom: 2 }}>
                              {viewCount != null && (
                                <span style={{ background: 'var(--bg-1)', border: '1px solid var(--line-1)', padding: '2px 8px', borderRadius: 'var(--r-xs)', fontSize: 'var(--text-3xs)', color: 'var(--fg-2)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                  👁️ {formatCompactNumber(viewCount)} visualizações
                                </span>
                              )}
                              {likeCount != null && (
                                <span style={{ background: 'var(--bg-1)', border: '1px solid var(--line-1)', padding: '2px 8px', borderRadius: 'var(--r-xs)', fontSize: 'var(--text-3xs)', color: 'var(--fg-2)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                  ❤️ {formatCompactNumber(likeCount)} curtidas
                                </span>
                              )}
                              {commentCount != null && (
                                <span style={{ background: 'var(--bg-1)', border: '1px solid var(--line-1)', padding: '2px 8px', borderRadius: 'var(--r-xs)', fontSize: 'var(--text-3xs)', color: 'var(--fg-2)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                  💬 {formatCompactNumber(commentCount)} comentários
                                </span>
                              )}
                              {repostCount != null && (
                                <span style={{ background: 'var(--bg-1)', border: '1px solid var(--line-1)', padding: '2px 8px', borderRadius: 'var(--r-xs)', fontSize: 'var(--text-3xs)', color: 'var(--fg-2)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                  🔁 {formatCompactNumber(repostCount)} compartilhamentos
                                </span>
                              )}
                            </div>
                          )}
                          {originalCaption && (
                            <div style={{ marginTop: 2 }}>
                              <strong style={{ color: 'var(--fg-3)', display: 'block', marginBottom: 4 }}>Descrição Original:</strong>
                              <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-sm)', padding: '8px 10px', maxHeight: 80, overflowY: 'auto', color: 'var(--fg-2)', lineHeight: 1.4 }}>
                                {originalCaption}
                              </div>
                            </div>
                          )}
                          {originalTags && originalTags.length > 0 && (
                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                              {originalTags.map((t, idx) => (
                                <span key={idx} style={{ background: 'rgba(10,129,217,.12)', color: 'var(--blue-300)', padding: '2px 6px', borderRadius: 4, fontSize: 'var(--text-3xs)' }}>
                                  {t.startsWith('#') ? t : `#${t}`}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* SUB-TAB 2: TELEMETRIA DA LLM */}
                  {obsSubTab === 'telemetry' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                      {/* 6 Metric Stat Cards */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-sm)', padding: '8px 12px' }}>
                          <span style={{ fontSize: 'var(--text-3xs)', color: 'var(--fg-3)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: 2 }}>Modelo</span>
                          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--blue-400, #60a5fa)', wordBreak: 'break-all' }}>{modelUsed}</span>
                        </div>
                        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-sm)', padding: '8px 12px' }}>
                          <span style={{ fontSize: 'var(--text-3xs)', color: 'var(--fg-3)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: 2 }}>Prompt Tokens</span>
                          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--fg-1)' }}>{promptTokens.toLocaleString()}</span>
                        </div>
                        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-sm)', padding: '8px 12px' }}>
                          <span style={{ fontSize: 'var(--text-3xs)', color: 'var(--fg-3)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: 2 }}>Candidate Tokens</span>
                          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--fg-1)' }}>{candidateTokens.toLocaleString()}</span>
                        </div>
                        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-sm)', padding: '8px 12px' }}>
                          <span style={{ fontSize: 'var(--text-3xs)', color: 'var(--fg-3)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: 2 }}>Total Tokens</span>
                          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--brand-blue)' }}>{totalTokens.toLocaleString()}</span>
                        </div>
                        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-sm)', padding: '8px 12px' }}>
                          <span style={{ fontSize: 'var(--text-3xs)', color: 'var(--fg-3)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: 2 }}>Custo Est. (USD)</span>
                          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--brand-teal, #34d399)' }}>${Number(estimatedCost).toFixed(5)}</span>
                        </div>
                        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-sm)', padding: '8px 12px' }}>
                          <span style={{ fontSize: 'var(--text-3xs)', color: 'var(--fg-3)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: 2 }}>Latência</span>
                          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--brand-amber, #fbbf24)' }}>{latencyMs} ms</span>
                        </div>
                      </div>

                      {/* Full Prompt Box */}
                      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-md)', padding: '12px 14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--fg-1)' }}>
                            Prompt Enviado à LLM
                          </span>
                          {fullPrompt && (
                            <Btn
                              variant="secondary"
                              size="xs"
                              icon={copiedKey === 'prompt' ? 'check' : 'copy'}
                              onClick={() => handleCopyText(fullPrompt, 'prompt', 'Prompt copiado')}
                            >
                              {copiedKey === 'prompt' ? 'Copiado!' : 'Copiar Prompt'}
                            </Btn>
                          )}
                        </div>
                        <pre
                          style={{
                            background: '#090d13',
                            border: '1px solid var(--line-1)',
                            borderRadius: 'var(--r-sm)',
                            padding: '10px 12px',
                            fontFamily: 'var(--font-mono, monospace)',
                            fontSize: 'var(--text-3xs)',
                            color: 'var(--fg-2)',
                            maxHeight: 140,
                            overflowY: 'auto',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            margin: 0,
                          }}
                        >
                          {fullPrompt || 'Prompt não registrado ou processamento ainda não iniciado.'}
                        </pre>
                      </div>

                      {/* Raw Response Box */}
                      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 'var(--r-md)', padding: '12px 14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                          <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--fg-1)' }}>
                            Resposta Bruta da IA (JSON)
                          </span>
                          {rawResponse && (
                            <Btn
                              variant="secondary"
                              size="xs"
                              icon={copiedKey === 'raw_response' ? 'check' : 'copy'}
                              onClick={() => handleCopyText(rawResponse, 'raw_response', 'Resposta copiada')}
                            >
                              {copiedKey === 'raw_response' ? 'Copiado!' : 'Copiar JSON'}
                            </Btn>
                          )}
                        </div>
                        <pre
                          style={{
                            background: '#090d13',
                            border: '1px solid var(--line-1)',
                            borderRadius: 'var(--r-sm)',
                            padding: '10px 12px',
                            fontFamily: 'var(--font-mono, monospace)',
                            fontSize: 'var(--text-3xs)',
                            color: 'var(--brand-teal, #34d399)',
                            maxHeight: 140,
                            overflowY: 'auto',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            margin: 0,
                          }}
                        >
                          {rawResponse || 'Resposta não registrada.'}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* SUB-TAB 3: LINHA DO TEMPO (LOGS CRONOLÓGICOS) */}
                  {obsSubTab === 'timeline' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>
                        Histórico cronológico de telemetria e atividades do pipeline:
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
                            const stageUpper = String(log.stage || '').toUpperCase();
                            const isError = log.level === 'error' || stageUpper === 'ERROR' || stageUpper === 'PUBLISH_ERROR' || stageUpper === 'FAILED';
                            const isWarn = log.level === 'warn';
                            const isSuccess = stageUpper === 'COMPLETE' || stageUpper === 'PUBLISHED' || stageUpper === 'APPROVE' || stageUpper === 'APPROVED' || stageUpper === 'RENDER_COMPLETE';
                            const isAi = stageUpper === 'AI_COPY';
                            const isContext = stageUpper === 'CONTEXT';
                            const isRender = stageUpper === 'RENDER' || stageUpper === 'RENDERING';
                            const isDownload = stageUpper === 'DOWNLOAD' || stageUpper === 'DOWNLOADING';
                            const stageColor = isError ? 'var(--brand-danger, #f87171)'
                              : isWarn ? 'var(--brand-amber, #fbbf24)'
                              : isSuccess ? 'var(--brand-teal, #34d399)'
                              : isAi ? '#c084fc'
                              : isContext ? '#38bdf8'
                              : isRender ? '#a78bfa'
                              : isDownload ? '#60a5fa'
                              : 'var(--blue-400, #60a5fa)';
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
              )}
            </div>
          </div>
        </div>

        {/* Lightbox / Zoom Overlay for Keyframe Image */}
        {zoomedKeyframe && (
          <div
            className="overlay"
            style={{ zIndex: 1000, background: 'rgba(0,0,0,0.88)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            onClick={() => setZoomedKeyframe(null)}
            role="presentation"
          >
            <div
              style={{ position: 'relative', maxWidth: '90vw', maxHeight: '90vh', display: 'flex', flexDirection: 'column', alignItems: 'center' }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                className="x"
                onClick={() => setZoomedKeyframe(null)}
                aria-label="Fechar zoom"
                style={{ position: 'absolute', top: -38, right: 0, color: '#fff', background: 'rgba(255,255,255,0.15)', borderRadius: '50%', padding: 6 }}
              >
                <Icon n="x" />
              </button>
              <img
                src={zoomedKeyframe}
                alt="Frame em alta resolução"
                style={{ maxHeight: '82vh', maxWidth: '88vw', objectFit: 'contain', borderRadius: 'var(--r-md)', border: '1px solid var(--line-1)', boxShadow: '0 20px 40px rgba(0,0,0,0.6)' }}
              />
              <div style={{ marginTop: 10, color: 'var(--fg-2)', fontSize: 'var(--text-xs)' }}>
                Frame extraído do vídeo original
              </div>
            </div>
          </div>
        )}

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
