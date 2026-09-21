// ClippyMe DiscoveryPanel — Busca e Descoberta de Vídeos Virais por Palavra-Chave / Hashtag
import { useState } from 'react';
import { Icon, Btn, Badge, Segmented } from './primitives';
import { searchViralVideos } from './discoveryApi';

const PLATFORMS = [
  { id: 'youtube', label: 'YouTube Shorts (Recomendado)', icon: 'youtube' },
  { id: 'instagram', label: 'Instagram Reels', icon: 'instagram' },
  { id: 'tiktok', label: 'TikTok', icon: 'video' },
];

const SORT_OPTIONS = [
  { id: 'virality_score', label: 'Score Viral 🔥' },
  { id: 'view_count', label: 'Mais Visualizados 👁️' },
  { id: 'engagement_rate', label: 'Maior Engajamento 📈' },
  { id: 'recent', label: 'Mais Recentes 🕒' },
];

const SUGGESTIONS = ['#politica', '#noticias', '#investimentos', '#curiosidades', '#tecnologia', '#humor'];

function formatMetric(num) {
  if (!num && num !== 0) return '0';
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}k`;
  return num.toString();
}

export function DiscoveryPanel({ onImportUrls, pushToast }) {
  const [query, setQuery] = useState('');
  const [platform, setPlatform] = useState('youtube');
  const [sortBy, setSortBy] = useState('virality_score');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = async (overrideQuery, overridePlatform, overrideSort) => {
    const q = (overrideQuery !== undefined ? overrideQuery : query).trim();
    const p = overridePlatform !== undefined ? overridePlatform : platform;
    const s = overrideSort !== undefined ? overrideSort : sortBy;
    if (!q) {
      pushToast?.('warn', 'Digite uma palavra-chave ou hashtag');
      return;
    }

    setLoading(true);
    setSelectedIds(new Set());
    try {
      const data = await searchViralVideos({
        query: q,
        platform: p,
        sort_by: s,
        limit: 20,
      });
      setResults(data.items || []);
      setHasSearched(true);
      if (!data.items?.length) {
        pushToast?.('info', 'Nenhum vídeo encontrado para essa busca.');
      } else {
        pushToast?.('success', `${data.items.length} vídeos virais encontrados!`);
      }
    } catch (err) {
      pushToast?.('error', err.message || 'Erro ao buscar vídeos');
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectTop5 = () => {
    const top5 = results.slice(0, 5).map((r) => r.id);
    setSelectedIds(new Set(top5));
  };

  const selectAll = () => {
    setSelectedIds(new Set(results.map((r) => r.id)));
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
  };

  const handleImport = () => {
    const selectedUrls = results
      .filter((r) => selectedIds.has(r.id))
      .map((r) => r.url);

    if (!selectedUrls.length) {
      pushToast?.('warn', 'Selecione ao menos um vídeo para importar');
      return;
    }

    onImportUrls(selectedUrls);
    pushToast?.('success', `${selectedUrls.length} vídeo(s) importado(s) para a criação!`);
  };

  return (
    <div className="disc-panel">
      {/* Platform & Search Header */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="disc-header">
          <Segmented
            value={platform}
            onChange={(p) => {
              setPlatform(p);
              if (query.trim()) handleSearch(undefined, p, undefined);
            }}
            options={PLATFORMS}
          />

          <div className="disc-sort">
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)' }}>Ordenar por:</span>
            <select
              value={sortBy}
              onChange={(e) => {
                setSortBy(e.target.value);
                if (hasSearched) handleSearch(undefined, undefined, e.target.value);
              }}
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>{opt.label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Input Bar */}
        <div className="input disc-input-row">
          <Icon n="search" />
          <input
            value={query}
            placeholder={
              platform === 'instagram'
                ? 'Buscar no Instagram (ex: politica, #eleicoes, noticias)...'
                : platform === 'tiktok'
                ? 'Buscar no TikTok (ex: politica, debatenacional)...'
                : 'Buscar no YouTube Shorts (ex: politica, discursos)...'
            }
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleSearch();
              }
            }}
          />
          <Btn variant="primary" icon="search" loading={loading} onClick={() => handleSearch()}>
            Buscar
          </Btn>
        </div>

        {/* Suggestions */}
        <div className="disc-sug-row">
          <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--fg-3)' }}>Sugestões:</span>
          {SUGGESTIONS.map((sug) => (
            <button
              key={sug}
              type="button"
              className="disc-sug-btn"
              onClick={() => {
                setQuery(sug);
                handleSearch(sug);
              }}
            >
              {sug}
            </button>
          ))}
        </div>
      </div>

      {/* Results Section */}
      {results.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Action Toolbar */}
          <div className="disc-toolbar">
            <div className="disc-toolbar-left">
              <Badge tone="proc">{results.length} encontrados</Badge>
              {selectedIds.size > 0 && (
                <Badge tone="top">{selectedIds.size} selecionado(s)</Badge>
              )}
            </div>

            <div className="disc-toolbar-right">
              <Btn size="sm" variant="ghost" onClick={selectTop5}>Top 5</Btn>
              <Btn size="sm" variant="ghost" onClick={selectAll}>Todos</Btn>
              {selectedIds.size > 0 && (
                <Btn size="sm" variant="ghost" onClick={clearSelection}>Limpar</Btn>
              )}
              <Btn
                size="sm"
                variant="primary"
                icon="plus"
                disabled={selectedIds.size === 0}
                onClick={handleImport}
              >
                Adicionar ao Lote {selectedIds.size > 0 ? `(${selectedIds.size})` : ''}
              </Btn>
            </div>
          </div>

          {/* Cards Grid */}
          <div className="disc-grid">
            {results.map((item) => {
              const isSelected = selectedIds.has(item.id);
              const isViral = item.virality_score >= 70;

              return (
                <div
                  key={item.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleSelect(item.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      toggleSelect(item.id);
                    }
                  }}
                  className={`disc-card ${isSelected ? 'selected' : ''}`}
                >
                  {/* Thumbnail / Media header */}
                  <div className="disc-media">
                    {item.thumbnail_url ? (
                      <img
                        src={item.thumbnail_url}
                        alt={item.title}
                        loading="lazy"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      <div className="disc-media-placeholder">
                        <Icon n="video" style={{ width: 32, height: 32 }} />
                      </div>
                    )}

                    {/* Selection Checkbox Badge */}
                    <div className="disc-chk">
                      {isSelected && <Icon n="check" style={{ width: 14, height: 14 }} />}
                    </div>

                    {/* Virality Score Badge */}
                    <div className="disc-score">
                      <Badge tone={isViral ? 'top' : 'proc'} icon="flame">
                        {item.virality_score}
                      </Badge>
                    </div>

                    {/* Metric overlay at bottom of thumbnail */}
                    <div className="disc-metrics">
                      <span>
                        <Icon n="eye" style={{ width: 12, height: 12 }} />
                        {formatMetric(item.view_count)}
                      </span>
                      <span>
                        <Icon n="heart" style={{ width: 12, height: 12 }} />
                        {formatMetric(item.like_count)}
                      </span>
                      <span>
                        <Icon n="message-square" style={{ width: 12, height: 12 }} />
                        {formatMetric(item.comment_count)}
                      </span>
                    </div>
                  </div>

                  {/* Card Body */}
                  <div className="disc-body">
                    <span className="disc-title" title={item.title}>
                      {item.title || 'Vídeo sem título'}
                    </span>
                    <span className="disc-author">
                      {item.author_handle || item.author_name}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Empty State Feedback */}
      {hasSearched && !loading && results.length === 0 && (
        <div
          style={{
            background: 'var(--bg-2)',
            border: '1px dashed var(--line-2)',
            borderRadius: 'var(--r-md)',
            padding: '24px 16px',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Icon n="search-x" style={{ width: 28, height: 28, color: 'var(--fg-4)' }} />
          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--fg-1)' }}>
            Nenhum vídeo retornado para &ldquo;{query}&rdquo;
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-3)', maxWidth: 440 }}>
            {platform === 'youtube'
              ? 'Tente termos mais populares como #politica, debate, noticias ou use palavras-chave mais abrangentes.'
              : 'Dica: o Instagram e TikTok exigem cookies salvos em Configurações para buscas de hashtags em lote. Você também pode usar a aba YouTube Shorts que busca diretamente sem restrições!'}
          </div>
          {platform !== 'youtube' && (
            <Btn
              size="sm"
              variant="secondary"
              icon="youtube"
              onClick={() => {
                setPlatform('youtube');
                handleSearch(query, 'youtube');
              }}
            >
              Buscar no YouTube Shorts
            </Btn>
          )}
        </div>
      )}
    </div>
  );
}
