// ClippyMe Discovery API client
import { apiFetch } from '../lib/apiToken';

export async function getDiscoveryPlatforms() {
  const res = await apiFetch('/api/discover/platforms');
  if (!res.ok) throw new Error(`Falha ao carregar plataformas (${res.status})`);
  return res.json();
}

export async function searchViralVideos({
  query,
  platform = 'instagram',
  limit = 20,
  min_views = null,
  sort_by = 'virality_score',
}) {
  const res = await apiFetch('/api/discover/search', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query,
      platform,
      limit,
      min_views: min_views ? Number(min_views) : null,
      sort_by,
    }),
  });

  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.detail || `Falha na busca (${res.status})`);
  }

  return res.json();
}
