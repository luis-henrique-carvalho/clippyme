import { test, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ViralStudioView } from './viralStudio.jsx';
import * as viralApi from './viralApi.js';

const getLocalAIModels = vi.fn(async () => ({
  lm_studio: { online: false, base_url: '', models: [] },
  ollama: { online: false, base_url: '', models: [] },
  models: [],
}));
const getConfig = vi.fn(async () => ({
  DEFAULT_AI_MODEL: '',
  GEMINI_MODEL: 'gemini-3.5-flash',
}));

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

vi.mock('./realApi', () => ({
  getLocalAIModels: (...a) => getLocalAIModels(...a),
  getConfig: (...a) => getConfig(...a),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('ViralStudioView renders standard AI model options when local servers are offline', async () => {
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

  const optgroupLabels = Array.from(modelSelect.querySelectorAll('optgroup')).map((g) => g.label);
  expect(optgroupLabels).toContain('⚪ IA Local (Desconectada)');
  expect(optgroupLabels).toContain('Google Gemini (Nuvem)');

  // Summary bar initially shows 'Padrão Gemini' chip
  expect(screen.getByText('Padrão Gemini')).toBeInTheDocument();

  // Change model to Gemini 3.5 Flash
  fireEvent.change(modelSelect, { target: { value: 'gemini:gemini-3.5-flash' } });

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
        model: 'gemini:gemini-3.5-flash',
        items: [
          expect.objectContaining({
            source_url: 'https://www.instagram.com/reel/DEMO123/',
          }),
        ],
      })
    );
  });
});

test('ViralStudioView dynamically renders connected LM Studio and Ollama optgroups', async () => {
  getLocalAIModels.mockResolvedValue({
    lm_studio: {
      online: true,
      base_url: 'http://localhost:1234',
      models: [{ id: 'qwen2.5-7b-instruct', name: 'Qwen 2.5 7B' }],
    },
    ollama: {
      online: true,
      base_url: 'http://localhost:11434',
      models: [{ id: 'llama3.2:latest', name: 'Llama 3.2' }],
    },
    models: [
      { id: 'lmstudio:qwen2.5-7b-instruct', name: 'Qwen 2.5 7B', provider: 'lm_studio', group: 'LM Studio' },
      { id: 'ollama:llama3.2:latest', name: 'Llama 3.2', provider: 'ollama', group: 'Ollama' },
    ],
  });

  const pushToast = vi.fn();
  render(<ViralStudioView pushToast={pushToast} />);

  await waitFor(() => expect(getLocalAIModels).toHaveBeenCalled());

  const newBatchBtn = screen.getByRole('button', { name: /Novo Lote/i });
  fireEvent.click(newBatchBtn);

  const modelSelect = screen.getByDisplayValue('Padrão (Configurações)');
  await waitFor(() => {
    const optgroups = Array.from(modelSelect.querySelectorAll('optgroup')).map((g) => g.label);
    expect(optgroups).toContain('🟢 LM Studio Conectado (1)');
    expect(optgroups).toContain('🟢 Ollama Conectado (1)');
  });

  // Select LM Studio dynamic model
  fireEvent.change(modelSelect, { target: { value: 'lmstudio:qwen2.5-7b-instruct' } });
  expect(screen.getByText('Qwen 2.5 7B')).toBeInTheDocument();
});
