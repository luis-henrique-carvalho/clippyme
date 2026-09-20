import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { ViralEditModal } from './ViralEditModal';

const sampleItem = {
  id: 'item-123456',
  source_url: 'https://www.instagram.com/reel/C12345/',
  product_code: '5566',
  selected_headline: 'Headline Incrível! 😱',
  caption: 'Legenda do item',
  keyframe_urls: [
    '/videos/viral_studio/batch-01/item-123456/keyframes/scene_0.jpg',
    '/videos/viral_studio/batch-01/item-123456/keyframes/scene_1.jpg',
  ],
  source_metadata: {
    title: 'Aspirador Portátil Sem Fio',
    description: 'Limpa tudo super rápido! Link na bio',
    uploader: '@achadinhos_oficial',
    tags: ['#aspirador', '#casa'],
  },
  ai_copy: {
    product: 'Aspirador Portátil Sem Fio',
    product_description: 'Aspirador leve e compacto',
    headlines: [
      'Headline Incrível! 😱',
      'Segunda Opção',
      'Terceira Opção',
      'Quarta Opção',
      'Quinta Opção',
    ],
    selected_headline: 'Headline Incrível! 😱',
    caption: 'Legenda completa',
    hashtags: ['#achadinhos'],
  },
  ai_context_summary: {
    scenes_count: 2,
    keyframes_count: 2,
    has_audio: true,
    transcript: 'Olha a potência desse aspirador portátil para limpar o sofá e o carro.',
    transcript_words: 13,
    has_original_caption: true,
    duration: 22.4,
  },
  ai_telemetry: {
    model: 'gemini-2.5-flash',
    prompt_tokens: 1240,
    candidate_tokens: 320,
    total_tokens: 1560,
    estimated_cost_usd: 0.00117,
    latency_ms: 840,
    prompt: 'Você é um especialista em marketing de afiliados brasileiro...',
    raw_response: '{\n  "product": "Aspirador Portátil Sem Fio"\n}',
  },
  logs: [
    {
      timestamp: '2026-09-20T18:00:00Z',
      stage: 'INIT',
      level: 'info',
      message: 'Iniciando processamento',
    },
    {
      timestamp: '2026-09-20T18:00:02Z',
      stage: 'DOWNLOAD',
      level: 'info',
      message: 'Download concluído (1240 KB)',
    },
    {
      timestamp: '2026-09-20T18:00:04Z',
      stage: 'CONTEXT',
      level: 'info',
      message: 'Contexto extraído: 2 cenas detectadas',
    },
    {
      timestamp: '2026-09-20T18:00:05Z',
      stage: 'AI_COPY',
      level: 'info',
      message: 'Copy comercial gerada com sucesso',
    },
    {
      timestamp: '2026-09-20T18:00:06Z',
      stage: 'COMPLETE',
      level: 'info',
      message: 'Vídeo renderizado com sucesso',
    },
  ],
};

const sampleBrand = {
  name: 'Vale o Clique?',
  handle: '@valeoclique',
  default_cta: 'Confira no link da bio!',
};

test('ViralEditModal displays context badges on Headlines tab and switches to Observabilidade & IA', () => {
  render(
    <ViralEditModal
      item={sampleItem}
      brand={sampleBrand}
      template={{ name: 'Classic Affiliate' }}
      onClose={vi.fn()}
      onSave={vi.fn()}
      onReRender={vi.fn()}
      onApprove={vi.fn()}
      pushToast={vi.fn()}
    />
  );

  // Check context badges on default Headlines tab
  expect(screen.getByText(/2 cenas \(2 frames\)/i)).toBeInTheDocument();
  expect(screen.getByText(/Áudio com fala/i)).toBeInTheDocument();
  expect(screen.getByText(/Post original capturado/i)).toBeInTheDocument();
  expect(screen.getByText(/22\.4s/i)).toBeInTheDocument();

  // Click "Observabilidade & IA" tab
  const obsTabBtn = screen.getByRole('button', { name: /Observabilidade & IA/i });
  fireEvent.click(obsTabBtn);

  // By default, Sinais Extraídos sub-tab is active
  expect(screen.getByText(/Frames Extraídos por Cena \(2 frames\)/i)).toBeInTheDocument();
  expect(screen.getByText(/Transcrição de Áudio/i)).toBeInTheDocument();
  expect(screen.getByText(/Olha a potência desse aspirador portátil/i)).toBeInTheDocument();
  expect(screen.getByText(/Aspirador Portátil Sem Fio/i)).toBeInTheDocument();
  expect(screen.getByText(/@achadinhos_oficial/i)).toBeInTheDocument();
});

test('ViralEditModal supports keyframe zoom lightbox', () => {
  render(
    <ViralEditModal
      item={sampleItem}
      brand={sampleBrand}
      onClose={vi.fn()}
      onSave={vi.fn()}
    />
  );

  fireEvent.click(screen.getByRole('button', { name: /Observabilidade & IA/i }));

  // Find first keyframe frame button and click to zoom
  const kfButtons = screen.getAllByTitle(/Cena \d+ - Clique para zoom/i);
  expect(kfButtons.length).toBe(2);
  fireEvent.click(kfButtons[0]);

  // Lightbox overlay is visible
  expect(screen.getByAltText(/Frame em alta resolução/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/Fechar zoom/i)).toBeInTheDocument();

  // Close zoom
  fireEvent.click(screen.getByLabelText(/Fechar zoom/i));
  expect(screen.queryByAltText(/Frame em alta resolução/i)).not.toBeInTheDocument();
});

test('ViralEditModal renders Telemetria da LLM metric cards and prompt/response codeboxes', () => {
  render(
    <ViralEditModal
      item={sampleItem}
      brand={sampleBrand}
      onClose={vi.fn()}
      onSave={vi.fn()}
    />
  );

  fireEvent.click(screen.getByRole('button', { name: /Observabilidade & IA/i }));

  // Switch to Telemetria da LLM sub-tab
  const telemetrySubTab = screen.getByRole('tab', { name: /Telemetria da LLM/i });
  fireEvent.click(telemetrySubTab);

  expect(screen.getByText('gemini-2.5-flash')).toBeInTheDocument();
  expect(screen.getByText(/1[.,]240/)).toBeInTheDocument();
  expect(screen.getByText('320')).toBeInTheDocument();
  expect(screen.getByText(/1[.,]560/)).toBeInTheDocument();
  expect(screen.getByText(/\$0\.00117/)).toBeInTheDocument();
  expect(screen.getByText('840 ms')).toBeInTheDocument();
  expect(screen.getByText(/Você é um especialista em marketing/i)).toBeInTheDocument();
});

test('ViralEditModal renders Linha do Tempo with terminal logs', () => {
  render(
    <ViralEditModal
      item={sampleItem}
      brand={sampleBrand}
      onClose={vi.fn()}
      onSave={vi.fn()}
    />
  );

  fireEvent.click(screen.getByRole('button', { name: /Observabilidade & IA/i }));

  // Switch to Linha do Tempo sub-tab
  const timelineSubTab = screen.getByRole('tab', { name: /Linha do Tempo/i });
  fireEvent.click(timelineSubTab);

  expect(screen.getByText(/Iniciando processamento/i)).toBeInTheDocument();
  expect(screen.getByText(/Download concluído/i)).toBeInTheDocument();
  expect(screen.getByText(/Contexto extraído: 2 cenas detectadas/i)).toBeInTheDocument();
  expect(screen.getByText(/Copy comercial gerada com sucesso/i)).toBeInTheDocument();
  expect(screen.getByText(/Vídeo renderizado com sucesso/i)).toBeInTheDocument();
  expect(screen.getByText(/\[INIT\]/i)).toBeInTheDocument();
  expect(screen.getByText(/\[COMPLETE\]/i)).toBeInTheDocument();
});

test('ViralEditModal renders empty logs state gracefully', () => {
  const emptyItem = {
    id: 'item-empty',
    source_url: 'https://www.tiktok.com/@user/video/1',
    logs: [],
  };

  render(
    <ViralEditModal
      item={emptyItem}
      onClose={vi.fn()}
      onSave={vi.fn()}
    />
  );

  fireEvent.click(screen.getByRole('button', { name: /Observabilidade & IA/i }));
  fireEvent.click(screen.getByRole('tab', { name: /Linha do Tempo/i }));

  expect(screen.getByText(/Nenhum log registrado para este item/i)).toBeInTheDocument();
});

