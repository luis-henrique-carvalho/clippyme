// Frontend API client for Viral Content Studio endpoints.
// Mirrors established conventions in realApi.js (apiFetch, safeResolveUrl, getApiUrl).
import { getApiUrl } from '../config.js';
import { apiFetch } from '../lib/apiToken.js';

function safeResolveUrl(url) {
  const raw = url || '';
  try {
    const u = new URL(raw, window.location.origin);
    if (u.protocol === 'http:' || u.protocol === 'https:') {
      return /^https?:\/\//i.test(raw) ? raw : getApiUrl(raw);
    }
  } catch { /* fallback to backend-relative */ }
  return getApiUrl(raw);
}

export function viralVideoSrc(item) {
  if (!item?.batch_id || !item?.id) return '';
  const basePath = `/videos/viral_studio/${item.batch_id}/${item.id}/rendered.mp4`;
  const bust = item.updated_at ? new Date(item.updated_at).getTime() : Date.now();
  return `${safeResolveUrl(basePath)}?v=${bust}`;
}

export async function getBrands() {
  const res = await apiFetch(getApiUrl('/api/viral-studio/brands'));
  if (!res.ok) throw new Error(`Failed to load brands (${res.status})`);
  return res.json();
}

export async function createBrand(payload) {
  const res = await apiFetch(getApiUrl('/api/viral-studio/brands'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create brand (${res.status})`);
  }
  return res.json();
}

export async function updateBrand(id, payload) {
  const res = await apiFetch(getApiUrl(`/api/viral-studio/brands/${id}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to update brand (${res.status})`);
  }
  return res.json();
}

export async function getTemplates() {
  const res = await apiFetch(getApiUrl('/api/viral-studio/templates'));
  if (!res.ok) throw new Error(`Failed to load templates (${res.status})`);
  return res.json();
}

export async function listBatches() {
  const res = await apiFetch(getApiUrl('/api/viral-studio/batches'));
  if (!res.ok) throw new Error(`Failed to list batches (${res.status})`);
  return res.json();
}

export async function getBatch(id) {
  const res = await apiFetch(getApiUrl(`/api/viral-studio/batches/${id}`));
  if (!res.ok) throw new Error(`Failed to get batch (${res.status})`);
  return res.json();
}

export async function createBatch({ brand_id, template_id, model, items }) {
  const res = await apiFetch(getApiUrl('/api/viral-studio/batches'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      brand_id,
      template_id: template_id || undefined,
      model: model || undefined,
      items,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create batch (${res.status})`);
  }
  return res.json();
}

export async function getItem(id) {
  const res = await apiFetch(getApiUrl(`/api/viral-studio/items/${id}`));
  if (!res.ok) throw new Error(`Failed to get item (${res.status})`);
  return res.json();
}

export async function updateItem(id, payload) {
  const res = await apiFetch(getApiUrl(`/api/viral-studio/items/${id}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to update item (${res.status})`);
  }
  return res.json();
}

export async function renderItem(id, payload = {}) {
  const res = await apiFetch(getApiUrl(`/api/viral-studio/items/${id}/render`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      headline: payload.headline || undefined,
      template_id: payload.template_id || undefined,
      watermark: payload.watermark !== undefined ? payload.watermark : true,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to queue render (${res.status})`);
  }
  return res.json();
}

export async function approveItem(id) {
  const res = await apiFetch(getApiUrl(`/api/viral-studio/items/${id}/approve`), {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to approve item (${res.status})`);
  }
  return res.json();
}

export async function retryItem(id) {
  const res = await apiFetch(getApiUrl(`/api/viral-studio/items/${id}/retry`), {
    method: 'POST',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to retry item (${res.status})`);
  }
  return res.json();
}

export async function publishViralItems({ item_ids, platforms, schedule_mode = 'now', scheduled_for, timezone, start_date }) {
  const res = await apiFetch(getApiUrl('/api/viral-studio/publish'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      item_ids,
      platforms,
      schedule_mode,
      scheduled_for: scheduled_for || undefined,
      timezone: timezone || undefined,
      start_date: start_date || undefined,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to publish items (${res.status})`);
  }
  return res.json();
}
