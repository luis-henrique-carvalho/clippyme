import { describe, it, expect } from 'vitest';
import { viralVideoSrc } from './viralApi.js';

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
