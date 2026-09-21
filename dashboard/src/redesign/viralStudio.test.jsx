import { test, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ViralStudioView } from './viralStudio.jsx';
import * as viralApi from './viralApi.js';

vi.mock('./viralApi.js', () => ({
  getBrands: vi.fn(async () => ({ brands: [{ id: 'brand-1', name: 'Brand 1', handle: '@b1' }] })),
  createBrand: vi.fn(),
  getTemplates: vi.fn(async () => ({ templates: [{ id: 'classic-affiliate', name: 'Classic Affiliate' }] })),
  listBatches: vi.fn(async () => ({ batches: [] })),
  getBatch: vi.fn(),
  createBatch: vi.fn(async (payload) => ({ id: 'batch-123', ...payload, items: [] })),
  updateItem: vi.fn(),
  renderItem: vi.fn(),
  approveItem: vi.fn(),
  retryItem: vi.fn(),
  viralVideoSrc: vi.fn(() => '/mock/video.mp4'),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('ViralStudioView renders AI model options grouped by provider and passes selected model to createBatch', async () => {
  const pushToast = vi.fn();
  render(<ViralStudioView pushToast={pushToast} />);

  // Wait for initial data load
  await waitFor(() => expect(viralApi.getBrands).toHaveBeenCalled());

  // Click on "Novo Lote" to open creation view
  const newBatchBtn = screen.getByRole('button', { name: /Novo Lote/i });
  fireEvent.click(newBatchBtn);

  // Verify Model selector exists with optgroups
  const modelSelect = screen.getByDisplayValue('Padrão (Configurações)');
  expect(modelSelect).toBeInTheDocument();

  const optgroups = modelSelect.querySelectorAll('optgroup');
  expect(optgroups[0].label).toBe('Google Gemini (Nuvem)');
  expect(optgroups[1].label).toBe('Ollama (Local / Gratuito)');
  expect(screen.getByText('Llama 3.2 (Local)')).toBeInTheDocument();

  // Summary bar initially shows 'Padrão Gemini' chip
  expect(screen.getByText('Padrão Gemini')).toBeInTheDocument();

  // Change model to Ollama Llama 3.2
  fireEvent.change(modelSelect, { target: { value: 'ollama:llama3.2' } });
  expect(screen.getAllByText('Llama 3.2 (Local)')).toHaveLength(2);

  // Add a URL
  const textarea = screen.getByPlaceholderText(/shorts\/exemplo1/i);
  fireEvent.change(textarea, {
    target: { value: 'https://www.instagram.com/reel/DEMO123/\n' },
  });

  // Verify detected video appears
  await waitFor(() => expect(screen.getByText('https://www.instagram.com/reel/DEMO123/')).toBeInTheDocument());

  // Click generate button
  const generateBtn = screen.getByRole('button', { name: /Gerar Vídeos/i });
  fireEvent.click(generateBtn);

  await waitFor(() => {
    expect(viralApi.createBatch).toHaveBeenCalledWith(
      expect.objectContaining({
        brand_id: 'brand-1',
        template_id: 'classic-affiliate',
        model: 'ollama:llama3.2',
        items: [
          expect.objectContaining({
            source_url: 'https://www.instagram.com/reel/DEMO123/',
          }),
        ],
      })
    );
  });
});
