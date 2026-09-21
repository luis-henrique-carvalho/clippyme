// ClippyMe redesign — Viral Content Studio View
// Redesigned with frontend-design skill principles and matching the native ClippyMe look:
// - Batch Grid: 9:16 vertical cards, flame/status badges, action footer identical to results.jsx.
// - Modal editing: Sleek ViralEditModal for deep curation of headlines, captions, and product codes.
// - Ingestion: Elegant single/batch creator inspired by create.jsx.
import { useState, useEffect, useMemo, useCallback } from 'react';
import { Icon, Btn, Panel, Segmented, Badge } from './primitives';
import { Hero } from './chrome';
import { relTime } from '../lib/relTime';
import { LazyVideo } from './LazyVideo';
import { ViralEditModal } from './ViralEditModal';
import { DiscoveryPanel } from './DiscoveryPanel';
import { AI_MODELS } from './data';
import {
  getBrands,
  createBrand,
  getTemplates,
  listBatches,
  getBatch,
  createBatch,
  updateItem,
  renderItem,
  approveItem,
  retryItem,
  viralVideoSrc,
} from './viralApi';

const STATUS_CONFIG = {
  PENDING: { label: 'Na fila', tone: 'out', icon: 'clock' },
  DOWNLOADING: { label: 'Baixando', tone: 'proc', icon: 'loader' },
  ANALYZING: { label: 'IA analisando', tone: 'proc', icon: 'sparkles' },
  RENDERING: { label: 'Renderizando', tone: 'proc', icon: 'loader' },
  READY_FOR_REVIEW: { label: 'Pronto', tone: 'top', icon: 'flame' },
  APPROVED: { label: 'Aprovado', tone: 'kept', icon: 'check' },
  SCHEDULED: { label: 'Agendado', tone: 'kept', icon: 'calendar' },
  PUBLISHED: { label: 'Publicado', tone: 'grad', icon: 'check' },
  FAILED: { label: 'Falhou', tone: 'danger', icon: 'triangle-alert' },
};

function ViralClipCard({
  item,
  brand: _brand,
  template: _template,
  selectMode,
  selected,
  onToggleSelect,
  onEdit,
  onReRender: _onReRender,
  onApprove,
  onPublishSingle,
  pushToast,
}) {
  const [downloading, setDownloading] = useState(false);
  const statusCfg = STATUS_CONFIG[item.status] || STATUS_CONFIG.PENDING;
  const isBusy = item.status === 'DOWNLOADING' || item.status === 'ANALYZING' || item.status === 'RENDERING';
  const title = item.selected_headline || item.product_code || 'Vídeo Comercial';
  const videoSrc = viralVideoSrc(item);

  const handleDownload = () => {
    if (!item.rendered_path) return;
    setDownloading(true);
    try {
      const a = document.createElement('a');
      a.href = videoSrc;
      a.download = `${title.slice(0, 30)}.mp4`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      pushToast?.('success', 'Download iniciado');
    } catch {
      pushToast?.('error', 'Falha ao baixar vídeo');
    } finally {
      setDownloading(false);
    }
  };

  const handleCopyCaption = () => {
    if (!item.caption) return;
    navigator.clipboard.writeText(item.caption)
      .then(() => pushToast?.('success', 'Legenda copiada para a área de transferência!'))
      .catch(() => pushToast?.('warn', 'Não foi possível copiar legenda.'));
  };

  return (
    <article
      className={`clip${item.status === 'APPROVED' || item.status === 'READY_FOR_REVIEW' ? ' top' : ''}${selectMode && selected ? ' sel' : ''}`}
      onClick={selectMode ? () => onToggleSelect(item.id) : undefined}
    >
      <div className="clip-media" style={{ padding: 0, background: '#000' }}>
        {item.rendered_path ? (
          <LazyVideo
            src={videoSrc}
            controls={!selectMode}
            playsInline
            muted={selectMode}
            aria-label={`Preview ${title}`}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', zIndex: 0 }}
          />
        ) : (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-3)', gap: 8, padding: 16, textAlign: 'center' }}>
            <Icon n={isBusy ? 'loader' : 'video'} style={{ width: 28, height: 28 }} />
            <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--fg-2)' }}>{statusCfg.label}</span>
          </div>
        )}

        {/* Top Badges (Flame Status + Product Code) */}
        <div className="clip-top" style={{ padding: 10 }}>
          <span className="score">
            <Icon n={statusCfg.icon} />
            {item.status === 'APPROVED' ? 'Aprovado' : item.status === 'READY_FOR_REVIEW' ? 'Pronto' : statusCfg.label}
          </span>
          {selectMode ? (
            <span className="clip-check" aria-hidden="true">
              <Icon n="check" />
            </span>
          ) : (
            item.product_code && (
              <span className="rf-badge" title={`Código do Produto: ${item.product_code}`}>
                <Icon n="tag" />
                #{item.product_code}
              </span>
            )
          )}
        </div>

        {/* Bottom Metadata */}
        <div className="clip-bottom" style={{ padding: 10 }}>
          {item.status === 'PUBLISHED' && <span className="clip-pub"><Icon n="check" />publicado</span>}
          {item.status === 'APPROVED' && <span className="clip-pub" style={{ borderColor: 'var(--brand-blue)', color: 'var(--blue-300)' }}><Icon n="check" />aprovado</span>}
        </div>

        {/* Reprocessing / Loading overlay */}
        {isBusy && (
          <div className="clip-busy" role="status">
            <Icon n="loader" />
            <span>{statusCfg.label}…</span>
          </div>
        )}
      </div>

      {/* Main Action Button */}
      {!selectMode && (
        <button
          type="button"
          className="clip-edit"
          onClick={(e) => { e.stopPropagation(); onEdit(item); }}
          aria-label={isBusy ? `Ver progresso e logs de ${title}` : `Revisar & editar ${title}`}
          style={isBusy ? { background: 'rgba(255,255,255,0.06)', borderColor: 'rgba(255,255,255,0.12)' } : undefined}
        >
          <Icon n={isBusy ? 'terminal' : item.status === 'FAILED' ? 'alert-triangle' : 'sliders-horizontal'} />
          {isBusy ? 'Ver Progresso & Logs' : item.status === 'FAILED' ? 'Ver Erro & Logs' : 'Revisar & Editar'}
        </button>
      )}

      {/* Footer Title & Mini Action Buttons */}
      <div className="clip-foot">
        <span className="ttl" title={title}>{title}</span>
        {!selectMode && (
          <>
            {item.caption && (
              <button
                type="button"
                className="mini"
                title="Copiar legenda comercial"
                aria-label="Copiar legenda"
                onClick={(e) => { e.stopPropagation(); handleCopyCaption(); }}
              >
                <Icon n="copy" />
              </button>
            )}
            {item.rendered_path && (
              <button
                type="button"
                className="mini"
                title="Baixar vídeo MP4"
                aria-label="Baixar vídeo"
                disabled={downloading}
                onClick={(e) => { e.stopPropagation(); handleDownload(); }}
              >
                <Icon n={downloading ? 'loader' : 'download'} />
              </button>
            )}
            {item.status === 'READY_FOR_REVIEW' && (
              <button
                type="button"
                className="mini"
                title="Aprovar vídeo"
                aria-label="Aprovar vídeo"
                style={{ color: 'var(--brand-teal)' }}
                onClick={(e) => { e.stopPropagation(); onApprove(item); }}
              >
                <Icon n="check" />
              </button>
            )}
            {item.status === 'APPROVED' && (
              <button
                type="button"
                className="mini"
                title="Publicar nas redes"
                aria-label="Publicar vídeo"
                style={{ color: 'var(--blue-300)' }}
                onClick={(e) => { e.stopPropagation(); onPublishSingle(item); }}
              >
                <Icon n="send" />
              </button>
            )}
            {item.status === 'FAILED' && (
              <button
                type="button"
                className="mini"
                title="Tentar novamente"
                aria-label="Reprocessar item"
                onClick={(e) => { e.stopPropagation(); retryItem(item.id).then(() => pushToast?.('info', 'Tentando novamente…')); }}
              >
                <Icon n="refresh-cw" />
              </button>
            )}
          </>
        )}
      </div>
    </article>
  );
}

export function ViralStudioView({ onOpenPublish, pushToast }) {
  const [mode, setMode] = useState('dashboard'); // 'dashboard' | 'review' | 'create' | 'brands'
  const [brands, setBrands] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedBrandId, setSelectedBrandId] = useState('');
  const [selectedTemplateId, setSelectedTemplateId] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [batches, setBatches] = useState([]);
  const [activeBatchId, setActiveBatchId] = useState(null);
  const [activeBatch, setActiveBatch] = useState(null);
  const [brandFilter, setBrandFilter] = useState('ALL');

  // Ingestion state
  const [rawUrls, setRawUrls] = useState('');
  const [parsedItems, setParsedItems] = useState([]);
  const [creatingBatch, setCreatingBatch] = useState(false);
  const [ingestionSource, setIngestionSource] = useState('url'); // 'url' | 'discovery'

  // Selection mode & Edit modal state
  const [selectMode, setSelectMode] = useState(false);
  const [selectedItemIds, setSelectedItemIds] = useState(new Set());
  const [editingItem, setEditingItem] = useState(null);

  // Brand creator state
  const [newBrand, setNewBrand] = useState({
    name: '',
    handle: '',
    default_cta: 'Confira os achadinhos no link da bio!',
    default_affiliate_url: '',
  });

  const loadInitialData = useCallback(async () => {
    try {
      const [brandData, templateData, batchData] = await Promise.all([
        getBrands().catch(() => ({ brands: [] })),
        getTemplates().catch(() => ({ templates: [] })),
        listBatches().catch(() => ({ batches: [] })),
      ]);
      setBrands(brandData.brands || []);
      setTemplates(templateData.templates || []);
      const fetchedBatches = batchData.batches || [];
      setBatches(fetchedBatches);

      if (brandData.brands?.length > 0 && !selectedBrandId) {
        setSelectedBrandId(brandData.brands[0].id);
      }
      if (templateData.templates?.length > 0 && !selectedTemplateId) {
        setSelectedTemplateId(templateData.templates[0].id);
      }
      if (fetchedBatches.length > 0 && !activeBatchId) {
        setActiveBatchId(fetchedBatches[0].id);
      }
    } catch (err) {
      pushToast?.('error', `Falha ao carregar dados: ${err.message}`);
    }
  }, [selectedBrandId, selectedTemplateId, activeBatchId, pushToast]);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Polling for active batch status when in review mode
  useEffect(() => {
    if (!activeBatchId || mode !== 'review') return;
    let mounted = true;

    const poll = async () => {
      try {
        const data = await getBatch(activeBatchId);
        if (mounted) setActiveBatch(data);
      } catch { /* silent fail */ }
    };

    poll();
    const interval = setInterval(poll, 2500);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [activeBatchId, mode]);

  // Sync editingItem when activeBatch polls new logs / status
  useEffect(() => {
    if (!editingItem || !activeBatch?.items) return;
    const fresh = activeBatch.items.find((it) => it.id === editingItem.id);
    if (fresh && JSON.stringify(fresh) !== JSON.stringify(editingItem)) {
      setEditingItem(fresh);
    }
  }, [activeBatch, editingItem]);

  // Parse pasted URLs
  useEffect(() => {
    if (!rawUrls.trim()) return;
    const lines = rawUrls.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const urlPattern = /(https?:\/\/[^\s]+)/i;
    const newItems = [];

    lines.forEach((line, idx) => {
      const match = line.match(urlPattern);
      if (match) {
        const url = match[1];
        if (/(instagram\.com|instagr\.am|tiktok\.com|youtube\.com|youtu\.be)/i.test(url)) {
          newItems.push({
            id: `temp-${idx}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            source_url: url,
            product_code: '',
            product_url: '',
          });
        }
      }
    });

    if (newItems.length > 0) {
      setParsedItems((prev) => {
        const existing = new Set(prev.map((it) => it.source_url));
        const filtered = newItems.filter((it) => !existing.has(it.source_url));
        return [...prev, ...filtered];
      });
      setRawUrls('');
    }
  }, [rawUrls]);

  const handleCreateBatch = async () => {
    if (parsedItems.length === 0) {
      pushToast?.('warn', 'Adicione pelo menos um vídeo para iniciar o lote.');
      return;
    }
    setCreatingBatch(true);
    try {
      const payload = {
        brand_id: selectedBrandId,
        template_id: selectedTemplateId,
        model: selectedModel || undefined,
        items: parsedItems.map((it) => ({
          source_url: it.source_url,
          product_code: it.product_code?.trim() || undefined,
          product_url: it.product_url?.trim() || undefined,
        })),
      };
      const res = await createBatch(payload);
      pushToast?.('success', `Lote com ${parsedItems.length} vídeos iniciado!`);
      setParsedItems([]);
      setActiveBatchId(res.id);
      setActiveBatch(res);
      setMode('review');
      listBatches().then((b) => setBatches(b.batches || [])).catch(() => {});
    } catch (err) {
      pushToast?.('error', `Erro ao criar lote: ${err.message}`);
    } finally {
      setCreatingBatch(false);
    }
  };

  const handleOpenBatch = async (batchId) => {
    setActiveBatchId(batchId);
    try {
      const data = await getBatch(batchId);
      setActiveBatch(data);
    } catch { /* will poll in review mode */ }
    setMode('review');
  };

  const currentBrand = useMemo(() => {
    return brands.find((b) => b.id === (activeBatch?.brand_id || selectedBrandId)) || null;
  }, [brands, activeBatch, selectedBrandId]);

  const currentTemplate = useMemo(() => {
    return templates.find((t) => t.id === (activeBatch?.template_id || selectedTemplateId)) || null;
  }, [templates, activeBatch, selectedTemplateId]);

  const selectedModelLabel = useMemo(() => {
    if (!selectedModel) return 'Padrão Gemini';
    for (const group of AI_MODELS) {
      const found = group.options.find(([val]) => val === selectedModel);
      if (found) {
        return found[1].split(' · ')[0];
      }
    }
    return selectedModel;
  }, [selectedModel]);

  const items = activeBatch?.items || [];
  const readyCount = items.filter((it) => it.status === 'READY_FOR_REVIEW' || it.status === 'APPROVED' || it.status === 'PUBLISHED').length;
  const approvedCount = items.filter((it) => it.status === 'APPROVED').length;

  // KPI calculations across all batches
  const dashboardStats = useMemo(() => {
    let totalVideos = 0;
    let totalReady = 0;
    let totalPublished = 0;

    batches.forEach((b) => {
      const bItems = b.items || [];
      totalVideos += b.total_items || bItems.length;
      bItems.forEach((it) => {
        if (it.status === 'READY_FOR_REVIEW' || it.status === 'APPROVED' || it.status === 'PUBLISHED') {
          totalReady++;
        }
        if (it.status === 'PUBLISHED') {
          totalPublished++;
        }
      });
    });

    return {
      totalBatches: batches.length,
      totalVideos,
      totalReady,
      totalPublished,
      activeBrands: brands.length,
    };
  }, [batches, brands]);

  // Filtered batch list
  const filteredBatches = useMemo(() => {
    if (brandFilter === 'ALL') return batches;
    return batches.filter((b) => b.brand_id === brandFilter);
  }, [batches, brandFilter]);

  const toggleSelect = (id) => {
    setSelectedItemIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSaveItem = async (itemId, patch) => {
    await updateItem(itemId, patch);
    setActiveBatch((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((it) => (it.id === itemId ? { ...it, ...patch } : it)),
      };
    });
  };

  const handleReRenderItem = async (item, headlineText) => {
    await renderItem(item.id, {
      headline: headlineText,
      template_id: activeBatch?.template_id,
      watermark: true,
    });
    setActiveBatch((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((it) => (it.id === item.id ? { ...it, selected_headline: headlineText, status: 'RENDERING' } : it)),
      };
    });
  };

  const handleApproveItem = async (item) => {
    try {
      const updated = await approveItem(item.id);
      pushToast?.('success', 'Vídeo aprovado!');
      setActiveBatch((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          items: prev.items.map((it) => (it.id === item.id ? updated : it)),
        };
      });
    } catch (err) {
      pushToast?.('error', `Erro na aprovação: ${err.message}`);
    }
  };

  const handleSaveBrand = async (e) => {
    e.preventDefault();
    if (!newBrand.name || !newBrand.handle) {
      pushToast?.('warn', 'Informe nome e @handle da marca.');
      return;
    }
    try {
      const created = await createBrand(newBrand);
      pushToast?.('success', `Marca "${created.name}" criada com sucesso!`);
      setBrands((prev) => [...prev, created]);
      setSelectedBrandId(created.id);
      setNewBrand({
        name: '',
        handle: '',
        default_cta: 'Confira os achadinhos no link da bio!',
        default_affiliate_url: '',
      });
      setMode('dashboard');
    } catch (err) {
      pushToast?.('error', `Erro ao criar marca: ${err.message}`);
    }
  };

  return (
    <div className="container fade-in">
      {/* ============================================================ VIEW 1: DASHBOARD HUB */}
      {mode === 'dashboard' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 20, marginBottom: 24, flexWrap: 'wrap' }}>
            <Hero
              eyebrow="Achadinhos & Vídeos Virais"
              line1="Painel do"
              grad="Viral Studio"
              sub="Monitore lotes de conversão, métricas de produção e publique diretamente nas redes."
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginTop: 8 }}>
              <Btn variant="secondary" size="sm" icon="tag" onClick={() => setMode('brands')}>
                Marcas ({brands.length})
              </Btn>
              <Btn variant="grad" size="sm" icon="plus" onClick={() => setMode('create')}>
                Novo Lote
              </Btn>
            </div>
          </div>

          {/* Metric Insights KPI Cards */}
          <div className="viral-stats-grid">
            <div className="viral-stat-card">
              <div className="viral-stat-icon" style={{ color: 'var(--brand-teal)' }}>
                <Icon n="check" />
              </div>
              <div>
                <div className="viral-stat-val">{dashboardStats.totalReady}</div>
                <div className="viral-stat-lbl">Prontos p/ Revisão</div>
              </div>
            </div>

            <div className="viral-stat-card">
              <div className="viral-stat-icon" style={{ color: 'var(--blue-300)' }}>
                <Icon n="file-video" />
              </div>
              <div>
                <div className="viral-stat-val">{dashboardStats.totalVideos}</div>
                <div className="viral-stat-lbl">Vídeos Processados</div>
              </div>
            </div>

            <div className="viral-stat-card">
              <div className="viral-stat-icon" style={{ color: 'var(--brand-amber)' }}>
                <Icon n="layers" />
              </div>
              <div>
                <div className="viral-stat-val">{dashboardStats.totalBatches}</div>
                <div className="viral-stat-lbl">Lotes Cadastrados</div>
              </div>
            </div>

            <div className="viral-stat-card">
              <div className="viral-stat-icon" style={{ color: '#d946ef' }}>
                <Icon n="send" />
              </div>
              <div>
                <div className="viral-stat-val">{dashboardStats.totalPublished}</div>
                <div className="viral-stat-lbl">Vídeos Publicados</div>
              </div>
            </div>
          </div>

          {/* Batches Listing Panel */}
          <Panel
            pad={false}
            title="Lotes de Conteúdo"
            sub="Selecione um lote para revisar o estúdio 9:16, editar headlines ou publicar em massa."
            icon="layers"
            headRight={
              brands.length > 1 ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>Filtrar Marca:</span>
                  <select
                    className="key-input"
                    style={{ height: 34, width: 170, fontSize: 'var(--text-xs)' }}
                    value={brandFilter}
                    onChange={(e) => setBrandFilter(e.target.value)}
                  >
                    <option value="ALL">Todas as Marcas</option>
                    {brands.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null
            }
          >
            {filteredBatches.length === 0 ? (
              <div className="empty">
                <div className="ei"><Icon n="layers" /></div>
                <h3>Nenhum lote encontrado</h3>
                <p>Crie seu primeiro lote colhendo links do Reels ou TikTok para começar.</p>
                <div style={{ marginTop: 16 }}>
                  <Btn variant="primary" icon="plus" onClick={() => setMode('create')}>
                    Criar Primeiro Lote
                  </Btn>
                </div>
              </div>
            ) : (
              <div className="hlist">
                {filteredBatches.map((b) => {
                  const bBrand = brands.find((brand) => brand.id === b.brand_id);
                  const bItems = b.items || [];
                  const bReady = bItems.filter((it) => it.status === 'READY_FOR_REVIEW' || it.status === 'APPROVED' || it.status === 'PUBLISHED').length;
                  const bApproved = bItems.filter((it) => it.status === 'APPROVED').length;
                  const bPublished = bItems.filter((it) => it.status === 'PUBLISHED').length;
                  const total = b.total_items || bItems.length;
                  const isFinished = b.status === 'COMPLETED' || (total > 0 && bReady === total);

                  return (
                    <div
                      key={b.id}
                      className="viral-batch-row"
                      role="button"
                      tabIndex={0}
                      aria-label={`Abrir lote ${b.id.slice(0, 8)}`}
                      onClick={() => handleOpenBatch(b.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleOpenBatch(b.id);
                        }
                      }}
                    >
                      {/* Batch Main Info Row */}
                      <div className="viral-batch-main">
                        <div className="viral-batch-thumb" style={{ background: isFinished ? 'var(--grad-viral)' : 'var(--bg-3)' }}>
                          {bBrand ? bBrand.name.slice(0, 2) : 'VS'}
                        </div>

                        <div className="viral-batch-info">
                          <div className="viral-batch-title">
                            <span>{bBrand ? bBrand.name : 'Lote Comercial'}</span>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--fg-3)', fontWeight: 400 }}>
                              #{b.id.slice(0, 8)}
                            </span>
                            {bBrand?.handle && (
                              <Badge tone="out">{bBrand.handle}</Badge>
                            )}
                          </div>

                          <div className="viral-batch-meta">
                            <span>
                              <Icon n="file-video" style={{ width: 12, height: 12, verticalAlign: '-1px', marginRight: 4 }} />
                              {total} {total === 1 ? 'vídeo' : 'vídeos'}
                            </span>
                            <span>·</span>
                            <span style={{ color: bReady > 0 ? 'var(--brand-teal)' : 'inherit' }}>
                              {bReady}/{total} prontos
                            </span>
                            {bPublished > 0 && (
                              <>
                                <span>·</span>
                                <span style={{ color: 'var(--blue-300)' }}>{bPublished} publicados</span>
                              </>
                            )}
                            {b.created_at && (
                              <>
                                <span>·</span>
                                <span>{relTime(b.created_at)}</span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Actions & Status Pill */}
                      <div className="viral-batch-actions" onClick={(e) => e.stopPropagation()}>
                        {bPublished > 0 && (
                          <Badge tone="blue" icon="send">{bPublished} publicados</Badge>
                        )}
                        {bApproved > 0 && (
                          <Badge tone="teal" icon="check">{bApproved} aprovados</Badge>
                        )}
                        {b.status === 'PROCESSING' && (
                          <Badge tone="amber" icon="loader">Processando</Badge>
                        )}

                        <Btn
                          variant="secondary"
                          size="sm"
                          icon="sliders-horizontal"
                          onClick={() => handleOpenBatch(b.id)}
                        >
                          Abrir Estúdio
                        </Btn>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>
        </>
      )}

      {/* ============================================================ VIEW 2: REVIEW & GALLERY */}
      {mode === 'review' && (
        <>
          <div className="viral-review-head">
            <div className="vr-top-row">
              <Btn
                variant="secondary"
                size="sm"
                icon="arrow-left"
                onClick={() => {
                  setMode('dashboard');
                  listBatches().then((b) => setBatches(b.batches || [])).catch(() => {});
                }}
              >
                Painel de Lotes
              </Btn>

              <div className="vr-title-wrap">
                <h2>{readyCount} {readyCount === 1 ? 'vídeo pronto' : 'vídeos prontos'}</h2>
                <div className="results-sub" style={{ marginBottom: 0 }}>
                  {currentBrand ? `${currentBrand.name} (${currentBrand.handle})` : 'Marca'} · #{activeBatchId?.slice(0, 6) || 'Lote'}
                </div>
              </div>
            </div>

            <div className="vr-actions-row">
              {batches.length > 1 && (
                <select
                  className="key-input vr-batch-select"
                  value={activeBatchId || ''}
                  onChange={(e) => handleOpenBatch(e.target.value)}
                >
                  {batches.map((b) => (
                    <option key={b.id} value={b.id}>
                      Lote #{b.id.slice(0, 6)} ({b.total_items} vídeos)
                    </option>
                  ))}
                </select>
              )}

              <div className="vr-btn-group">
                <Btn
                  variant={selectMode ? 'primary' : 'secondary'}
                  icon="check-square"
                  onClick={() => {
                    setSelectMode(!selectMode);
                    setSelectedItemIds(new Set());
                  }}
                >
                  {selectMode ? 'Cancelar' : 'Selecionar'}
                </Btn>

                <Btn
                  variant="grad"
                  icon="sparkles"
                  disabled={approvedCount === 0}
                  onClick={() => {
                    const approved = items.filter((it) => it.status === 'APPROVED');
                    if (approved.length === 0) {
                      pushToast?.('warn', 'Nenhum vídeo aprovado no lote para publicar.');
                      return;
                    }
                    onOpenPublish?.(approved);
                  }}
                >
                  Publicar ({approvedCount})
                </Btn>
              </div>
            </div>
          </div>

          {/* Actionbar during select mode */}
          {selectMode && (
            <div className="actionbar">
              <span className="sel-n">{selectedItemIds.size} selecionado{selectedItemIds.size === 1 ? '' : 's'}</span>
              <div className="ab-right">
                <Btn
                  variant="secondary"
                  size="sm"
                  onClick={() => setSelectedItemIds(new Set(items.map((it) => it.id)))}
                >
                  Selecionar todos
                </Btn>
                <Btn
                  variant="grad"
                  size="sm"
                  disabled={selectedItemIds.size === 0}
                  onClick={() => {
                    const selList = items.filter((it) => selectedItemIds.has(it.id));
                    onOpenPublish?.(selList);
                  }}
                >
                  Publicar selecionados ({selectedItemIds.size})
                </Btn>
              </div>
            </div>
          )}

          {/* Clean 4-column Results Grid identical to the reference image */}
          {items.length === 0 ? (
            <div className="empty">
              <div className="ei"><Icon n="video" /></div>
              <h3>Nenhum vídeo no lote</h3>
              <p>Clique em &ldquo;Painel de Lotes&rdquo; ou crie um novo lote para adicionar vídeos.</p>
            </div>
          ) : (
            <div className="results-grid">
              {items.map((item) => (
                <ViralClipCard
                  key={item.id}
                  item={item}
                  brand={currentBrand}
                  template={currentTemplate}
                  selectMode={selectMode}
                  selected={selectedItemIds.has(item.id)}
                  onToggleSelect={toggleSelect}
                  onEdit={(it) => setEditingItem(it)}
                  onReRender={handleReRenderItem}
                  onApprove={handleApproveItem}
                  onPublishSingle={(it) => onOpenPublish?.([it])}
                  pushToast={pushToast}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* ============================================================ VIEW 3: CREATE BATCH (FLOW INSPIRADO NO CREATE.JSX) */}
      {mode === 'create' && (
        <div className="container narrow fade-in">
          <Hero
            eyebrow="Ingestão de Conteúdo · TikTok & Reels"
            line1="Links de produtos in."
            grad="Achadinhos virais out."
            sub="Cole links de Reels ou TikTok, configure a marca associada e gere automaticamente vídeos 9:16 com copy comercial de alta conversão."
          />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <Panel
              title="Origem dos Vídeos"
              sub="Cole uma ou várias URLs de Reels ou TikTok ou busque vídeos virais"
              icon="link"
              headRight={
                <Btn variant="ghost" size="sm" icon="arrow-left" onClick={() => setMode('dashboard')}>
                  Voltar ao Painel
                </Btn>
              }
            >
              <Segmented full value={ingestionSource} onChange={setIngestionSource}
                options={[
                  { id: 'url', label: 'URLs Diretas', icon: 'globe' },
                  { id: 'discovery', label: 'Busca Viral 🔥', icon: 'search' },
                ]} />
              <div style={{ height: 14 }} />

              {ingestionSource === 'discovery' ? (
                <DiscoveryPanel 
                  pushToast={pushToast} 
                  onImportUrls={(urls) => {
                    if (!urls || !urls.length) return;
                    const newItems = urls.map((url, idx) => ({
                      id: `disc-${idx}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
                      source_url: url,
                      product_code: '',
                      product_url: '',
                    }));
                    setParsedItems((prev) => {
                      const existing = new Set(prev.map((it) => it.source_url));
                      const filtered = newItems.filter((it) => !existing.has(it.source_url));
                      return [...prev, ...filtered];
                    });
                    pushToast?.('success', `${urls.length} vídeo(s) adicionado(s) ao lote! Pronto para gerar.`);
                  }} 
                />
              ) : (
                <div className="field">
                  <span className="field-label">
                    <Icon n="globe" /> URLs do YouTube Shorts, Instagram Reels ou TikTok · uma por linha
                  </span>
                  <div style={{ position: 'relative' }}>
                    <textarea
                      className="ta mono"
                      rows={4}
                      style={{ paddingRight: 90 }}
                      placeholder={'https://www.youtube.com/shorts/exemplo1\nhttps://www.instagram.com/reel/C_exemplo2\nhttps://www.tiktok.com/@perfil/video/7234567890'}
                      value={rawUrls}
                      onChange={(e) => setRawUrls(e.target.value)}
                    />
                    <button
                      type="button"
                      className="paste"
                      style={{ position: 'absolute', top: 10, right: 10 }}
                      onClick={async () => {
                        try {
                          const text = await navigator.clipboard.readText();
                          if (text) setRawUrls((prev) => (prev ? `${prev}\n${text}` : text));
                        } catch { /* clipboard blocked */ }
                      }}
                    >
                      <Icon n="clipboard" />Colar
                    </button>
                  </div>
                </div>
              )}

              {/* Parsed Videos List */}
              {parsedItems.length > 0 && (
                <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--line-1)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <span className="label" style={{ color: 'var(--brand-teal)' }}>
                      {parsedItems.length} {parsedItems.length === 1 ? 'Vídeo detectado' : 'Vídeos detectados'}
                    </span>
                    <button
                      type="button"
                      className="chip"
                      style={{ cursor: 'pointer', color: 'var(--danger)', background: 'none', border: 'none', font: 'inherit' }}
                      onClick={() => setParsedItems([])}
                    >
                      Limpar todos
                    </button>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {parsedItems.map((it, idx) => (
                      <div key={it.id} className="viral-parsed-item">
                        <div className="viral-parsed-item-top">
                          <span className="vpi-idx">
                            #{String(idx + 1).padStart(2, '0')}
                          </span>
                          <div className="vpi-url" title={it.source_url}>
                            {it.source_url}
                          </div>
                          <button
                            type="button"
                            className="mini"
                            title="Remover vídeo"
                            aria-label="Remover vídeo da lista"
                            onClick={() => setParsedItems((list) => list.filter((x) => x.id !== it.id))}
                          >
                            <Icon n="x" />
                          </button>
                        </div>
                        <div className="viral-parsed-item-bottom">
                          <input
                            type="text"
                            placeholder="Cód. Produto"
                            className="key-input"
                            value={it.product_code}
                            onChange={(e) => {
                              const val = e.target.value;
                              setParsedItems((list) => list.map((x) => (x.id === it.id ? { ...x, product_code: val } : x)));
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Panel>

            {/* Configuração da Marca, Template e Modelo de IA */}
            <Panel
              title="Marca & Template"
              sub="Personalize a assinatura comercial, estilo visual e modelo de inteligência artificial"
              icon="stamp"
            >
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
                <div className="field" style={{ marginBottom: 0 }}>
                  <span className="field-label">
                    <Icon n="tag" /> Marca Comercial
                  </span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <select
                      className="sel"
                      value={selectedBrandId}
                      onChange={(e) => setSelectedBrandId(e.target.value)}
                    >
                      {brands.map((b) => (
                        <option key={b.id} value={b.id}>{b.name} ({b.handle})</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      style={{ height: 42, padding: '0 12px' }}
                      title="Cadastrar nova marca"
                      onClick={() => setMode('brands')}
                    >
                      <Icon n="plus" />
                    </button>
                  </div>
                </div>

                <div className="field" style={{ marginBottom: 0 }}>
                  <span className="field-label">
                    <Icon n="sliders-horizontal" /> Template Visual 9:16
                  </span>
                  <select
                    className="sel"
                    value={selectedTemplateId}
                    onChange={(e) => setSelectedTemplateId(e.target.value)}
                  >
                    {templates.map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                </div>

                <div className="field" style={{ marginBottom: 0 }}>
                  <span className="field-label">
                    <Icon n="sparkles" /> Modelo de IA
                  </span>
                  <select
                    className="sel"
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                  >
                    <option value="">Padrão (Configurações)</option>
                    {AI_MODELS.map((group) => (
                      <optgroup key={group.group} label={group.group}>
                        {group.options.map(([val, lbl]) => (
                          <option key={val} value={val}>{lbl}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </div>
              </div>
            </Panel>
          </div>

          {/* Bottom Summary Bar identical to create.jsx */}
          <div className="summary" style={{ marginTop: 24 }}>
            <div>
              <div className="s-main">
                {parsedItems.length > 0
                  ? `Pronto para gerar ${parsedItems.length} vídeo${parsedItems.length === 1 ? '' : 's'} comercial${parsedItems.length === 1 ? '' : 'is'}`
                  : 'Cole links acima para iniciar o lote'}
              </div>
              <div className="s-sub">
                <span className="chip">9:16 Vertical</span>
                {currentBrand && <span className="chip">{currentBrand.name}</span>}
                {currentTemplate && <span className="chip">{currentTemplate.name}</span>}
                <span className="chip">{selectedModelLabel}</span>
              </div>
            </div>
            <div className="s-right">
              <Btn
                variant="grad"
                size="lg"
                icon="wand-sparkles"
                disabled={parsedItems.length === 0 || creatingBatch}
                loading={creatingBatch}
                onClick={handleCreateBatch}
              >
                Gerar Vídeos ({parsedItems.length})
              </Btn>
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ VIEW 4: BRAND MANAGER */}
      {mode === 'brands' && (
        <div className="container narrow fade-in">
          <Hero
            eyebrow="Identidade Comercial · Assinatura & Links"
            line1="Gerenciar"
            grad="Marcas & Perfis"
            sub="Cadastre os perfis que assinarão os vídeos verticais e personalize as chamadas para ação (CTA) e links de afiliado."
          />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <Panel
              title="Nova Marca"
              sub="Cadastre o perfil que assinará os vídeos"
              icon="plus"
              headRight={
                <Btn variant="ghost" size="sm" icon="arrow-left" onClick={() => setMode('dashboard')}>
                  Voltar ao Painel
                </Btn>
              }
            >
              <form onSubmit={handleSaveBrand}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14, marginBottom: 14 }}>
                  <div className="field" style={{ marginBottom: 0 }}>
                    <span className="field-label">Nome da Marca</span>
                    <input
                      type="text"
                      className="key-input"
                      style={{ width: '100%', height: 42, fontFamily: 'var(--font-sans)', fontSize: 'var(--text-sm)' }}
                      placeholder="Ex: Ofertas da Florzinha"
                      value={newBrand.name}
                      onChange={(e) => setNewBrand({ ...newBrand, name: e.target.value })}
                    />
                  </div>
                  <div className="field" style={{ marginBottom: 0 }}>
                    <span className="field-label">Handle (@)</span>
                    <input
                      type="text"
                      className="key-input"
                      style={{ width: '100%', height: 42, fontSize: 'var(--text-sm)' }}
                      placeholder="@florzinha"
                      value={newBrand.handle}
                      onChange={(e) => setNewBrand({ ...newBrand, handle: e.target.value })}
                    />
                  </div>
                </div>

                <div className="field">
                  <span className="field-label">CTA Padrão</span>
                  <input
                    type="text"
                    className="key-input"
                    style={{ width: '100%', height: 42, fontFamily: 'var(--font-sans)', fontSize: 'var(--text-sm)' }}
                    value={newBrand.default_cta}
                    onChange={(e) => setNewBrand({ ...newBrand, default_cta: e.target.value })}
                  />
                </div>

                <div className="field" style={{ marginBottom: 18 }}>
                  <span className="field-label">Link Padrão de Afiliado (Bio)</span>
                  <input
                    type="url"
                    className="key-input"
                    style={{ width: '100%', height: 42, fontSize: 'var(--text-sm)' }}
                    placeholder="https://linktr.ee/seuperfil"
                    value={newBrand.default_affiliate_url}
                    onChange={(e) => setNewBrand({ ...newBrand, default_affiliate_url: e.target.value })}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                  <Btn variant="grad" type="submit" icon="check">
                    Cadastrar Marca
                  </Btn>
                </div>
              </form>
            </Panel>

            <Panel
              title={`Marcas Ativas (${brands.length})`}
              sub="Perfis configurados para geração automática de copy e overlay"
              icon="tag"
            >
              {brands.length === 0 ? (
                <div className="empty" style={{ padding: '30px 20px' }}>
                  <p>Nenhuma marca cadastrada ainda.</p>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
                  {brands.map((b) => (
                    <div
                      key={b.id}
                      style={{
                        background: 'var(--bg-3)',
                        border: '1px solid var(--line-1)',
                        borderRadius: 'var(--r-md)',
                        padding: 16,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                        <div className="avatar" style={{ width: 36, height: 36, fontSize: 'var(--text-xs)' }}>
                          {b.name.slice(0, 2).toUpperCase()}
                        </div>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {b.name}
                          </div>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-2xs)', color: 'var(--blue-300)' }}>
                            {b.handle}
                          </div>
                        </div>
                      </div>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)', lineHeight: 1.4, marginTop: 4 }}>
                        {b.default_cta}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>
        </div>
      )}

      {/* ============================================================ MODAL DE EDIÇÃO FOCADO */}
      {editingItem && (
        <ViralEditModal
          item={editingItem}
          brand={currentBrand}
          template={currentTemplate}
          onClose={() => setEditingItem(null)}
          onSave={handleSaveItem}
          onReRender={handleReRenderItem}
          onApprove={handleApproveItem}
          pushToast={pushToast}
        />
      )}
    </div>
  );
}
