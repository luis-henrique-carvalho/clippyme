import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { ViralEditModal } from './ViralEditModal';

test('ViralEditModal displays context badges and switches to Logs & Atividade tab', () => {
  const sampleItem = {
    id: 'item-123456',
    source_url: 'https://www.instagram.com/reel/C12345/',
    product_code: '5566',
    selected_headline: 'Headline Incrível! 😱',
    caption: 'Legenda do item',
    ai_copy: {
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
      scenes_count: 4,
      keyframes_count: 4,
      has_audio: true,
      transcript_words: 28,
      has_original_caption: true,
      duration: 22.4,
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
        message: 'Contexto extraído: 4 cenas detectadas',
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
  expect(screen.getByText(/4 cenas \(4 frames\)/i)).toBeInTheDocument();
  expect(screen.getByText(/Áudio com fala/i)).toBeInTheDocument();
  expect(screen.getByText(/Post original capturado/i)).toBeInTheDocument();
  expect(screen.getByText(/22\.4s/i)).toBeInTheDocument();

  // Click "Logs & Atividade" tab
  const logsTabBtn = screen.getByRole('button', { name: /Logs & Atividade/i });
  fireEvent.click(logsTabBtn);

  // Verify terminal logs are rendered
  expect(screen.getByText(/Iniciando processamento/i)).toBeInTheDocument();
  expect(screen.getByText(/Download concluído/i)).toBeInTheDocument();
  expect(screen.getByText(/Contexto extraído: 4 cenas detectadas/i)).toBeInTheDocument();
  expect(screen.getByText(/Vídeo renderizado com sucesso/i)).toBeInTheDocument();
  expect(screen.getByText(/\[INIT\]/i)).toBeInTheDocument();
  expect(screen.getByText(/\[COMPLETE\]/i)).toBeInTheDocument();
});

test('ViralEditModal renders empty logs state gracefully', () => {
  const sampleItem = {
    id: 'item-empty',
    source_url: 'https://www.tiktok.com/@user/video/1',
    logs: [],
  };

  render(
    <ViralEditModal
      item={sampleItem}
      onClose={vi.fn()}
      onSave={vi.fn()}
    />
  );

  const logsTabBtn = screen.getByRole('button', { name: /Logs & Atividade/i });
  fireEvent.click(logsTabBtn);

  expect(screen.getByText(/Nenhum log registrado para este item/i)).toBeInTheDocument();
});
