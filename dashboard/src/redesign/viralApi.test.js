import { describe, it, expect, vi } from 'vitest';
import { viralVideoSrc, createBatch } from './viralApi.js';
import * as apiTokenModule from '../lib/apiToken.js';

describe('viralVideoSrc', () => {
  it('returns empty string if item is missing or lacks ids', () => {
    expect(viralVideoSrc(null)).toBe('');
    expect(viralVideoSrc({})).toBe('');
    expect(viralVideoSrc({ id: 'item1' })).toBe('');
    expect(viralVideoSrc({ batch_id: 'batch1' })).toBe('');
  });

  it('generates correct video streaming URL with cache buster', () => {
    const item = {
      id: 'item_123',
      batch_id: 'batch_456',
      updated_at: '2026-09-19T12:00:00Z',
    };
    const expectedTime = new Date('2026-09-19T12:00:00Z').getTime();
    const url = viralVideoSrc(item);
    expect(url).toContain('/videos/viral_studio/batch_456/item_123/rendered.mp4');
    expect(url).toContain(`v=${expectedTime}`);
  });
});

describe('createBatch', () => {
  it('includes model in request body when specified', async () => {
    const spy = vi.spyOn(apiTokenModule, 'apiFetch').mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'batch_789', model: 'lmstudio:prism-ml/bonsai-27b' }),
    });

    const result = await createBatch({
      brand_id: 'brand_1',
      template_id: 'template_1',
      model: 'lmstudio:prism-ml/bonsai-27b',
      items: [{ source_url: 'https://instagram.com/reel/123' }],
    });

    expect(spy).toHaveBeenCalled();
    const callArgs = spy.mock.calls[0];
    const body = JSON.parse(callArgs[1].body);
    expect(body.model).toBe('lmstudio:prism-ml/bonsai-27b');
    expect(body.brand_id).toBe('brand_1');
    expect(result.id).toBe('batch_789');

    spy.mockRestore();
  });
});
