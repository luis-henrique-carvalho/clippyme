// SettingsView key-status badges — pins the bug fix where the "set"/"empty"
// badge must reflect backend-confirmed `present` state, never the raw input
// text, and must refresh after save/clear instead of going stale or being
// wiped by a transient getConfig failure.
import { test, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { SettingsView, HistoryView } from './views.jsx';

const getConfig = vi.fn();
const saveConfig = vi.fn();
const cookiesStatus = vi.fn(async () => ({ configured: false, youtube: false, instagram: false, tiktok: false, legacy: false }));
const uploadPlatformCookies = vi.fn(async () => ({ status: 'ok' }));
const deletePlatformCookies = vi.fn(async () => ({ status: 'ok' }));

vi.mock('./realApi', () => ({
  getConfig: (...a) => getConfig(...a),
  saveConfig: (...a) => saveConfig(...a),
  getModels: vi.fn(async () => ({ models: [] })),
  cookiesStatus: (...a) => cookiesStatus(...a),
  uploadCookies: vi.fn(),
  deleteCookies: vi.fn(),
  uploadPlatformCookies: (...a) => uploadPlatformCookies(...a),
  deletePlatformCookies: (...a) => deletePlatformCookies(...a),
  getZernio: vi.fn(async () => ({ configured: false })),
  saveZernio: vi.fn(),
  discoverZernioAccounts: vi.fn(),
  listFonts: vi.fn(async () => ({ fonts: [] })),
  uploadFont: vi.fn(),
  deleteFont: vi.fn(),
  logoStatus: vi.fn(async () => ({ configured: false })),
  uploadLogo: vi.fn(),
  deleteLogo: vi.fn(),
}));

const EMPTY_CONFIG = { GEMINI_API_KEY: '', HF_TOKEN: '', DEEPGRAM_API_KEY: '', ELEVENLABS_API_KEY: '' };
const SET_CONFIG = { ...EMPTY_CONFIG, GEMINI_API_KEY: 'AIza...xyz1' };

beforeEach(() => {
  vi.clearAllMocks();
  saveConfig.mockResolvedValue({ success: true });
});

function mount(pushToast = vi.fn()) {
  render(<SettingsView pushToast={pushToast} />);
  return pushToast;
}

const geminiRow = () => screen.getByLabelText('Gemini').closest('.keyrow');

test('badge reflects backend state, not input text typed before any save', async () => {
  getConfig.mockResolvedValue(EMPTY_CONFIG);
  mount();
  await waitFor(() => expect(within(geminiRow()).getByText('empty')).toBeInTheDocument());

  // Typing into the field (no blur/save yet) must not flip the badge.
  fireEvent.change(screen.getByLabelText('Gemini'), { target: { value: 'AIzaSomeKey' } });
  expect(within(geminiRow()).getByText('empty')).toBeInTheDocument();
  expect(within(geminiRow()).queryByText('set')).toBeNull();
});

test('save triggers a refetch and the badge updates from the backend response', async () => {
  getConfig.mockResolvedValueOnce(EMPTY_CONFIG).mockResolvedValueOnce(SET_CONFIG);
  mount();
  await waitFor(() => expect(within(geminiRow()).getByText('empty')).toBeInTheDocument());

  const input = screen.getByLabelText('Gemini');
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: 'AIzaSomeKey' } });
  fireEvent.blur(input);

  expect(saveConfig).toHaveBeenCalledWith({ GEMINI_API_KEY: 'AIzaSomeKey' });
  await waitFor(() => expect(getConfig).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(within(geminiRow()).getByText('set')).toBeInTheDocument());
});

test('a failed post-save refetch does not wipe previously-known present state', async () => {
  getConfig.mockResolvedValueOnce(SET_CONFIG).mockResolvedValueOnce(null);
  const pushToast = mount();
  await waitFor(() => expect(within(geminiRow()).getByText('set')).toBeInTheDocument());

  const input = screen.getByLabelText('Deepgram');
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: 'dg_key' } });
  fireEvent.blur(input);

  await waitFor(() => expect(getConfig).toHaveBeenCalledTimes(2));
  // Gemini's badge (unrelated to the Deepgram save) must still read "set".
  expect(within(geminiRow()).getByText('set')).toBeInTheDocument();
  expect(pushToast).toHaveBeenCalledWith('warn', expect.any(String));
});

test('clearing a present key saves an empty value and the badge flips to empty', async () => {
  getConfig.mockResolvedValueOnce(SET_CONFIG).mockResolvedValueOnce(EMPTY_CONFIG);
  mount();
  await waitFor(() => expect(within(geminiRow()).getByText('set')).toBeInTheDocument());

  fireEvent.click(within(geminiRow()).getByRole('button', { name: 'Clear Gemini key' }));

  expect(saveConfig).toHaveBeenCalledWith({ GEMINI_API_KEY: '' });
  await waitFor(() => expect(within(geminiRow()).getByText('empty')).toBeInTheDocument());
});

test('Twitch client id/secret rows reflect backend present state', async () => {
  getConfig.mockResolvedValue({ ...EMPTY_CONFIG, TWITCH_CLIENT_ID: 'abcd1234', TWITCH_CLIENT_SECRET: 'shhh12345678' });
  mount();
  const idRow = () => screen.getByLabelText('Twitch client ID').closest('.keyrow');
  const secretRow = () => screen.getByLabelText('Twitch client secret').closest('.keyrow');
  await waitFor(() => expect(within(idRow()).getByText('set')).toBeInTheDocument());
  expect(within(secretRow()).getByText('set')).toBeInTheDocument();
});

test('Twitch client id/secret rows show empty when unset', async () => {
  getConfig.mockResolvedValue(EMPTY_CONFIG);
  mount();
  const idRow = () => screen.getByLabelText('Twitch client ID').closest('.keyrow');
  await waitFor(() => expect(within(idRow()).getByText('empty')).toBeInTheDocument());
});

// HistoryView — title + per-job "published" badge (derived from
// history_service.scan_history's additive `title`/`publishedCount` fields).
test('history row shows the video title and a published-count badge when clips were published', () => {
  const history = [
    { jobId: 'job-1', status: 'complete', clipCount: 2, source: 'my video', title: 'my video', publishedCount: 1, timestamp: Date.now() },
    { jobId: 'job-2', status: 'complete', clipCount: 3, source: 'other video', title: 'other video', publishedCount: 0, timestamp: Date.now() },
  ];
  render(<HistoryView history={history} availableIds={null} onOpen={vi.fn()} onDelete={vi.fn()} onClear={vi.fn()} />);

  expect(screen.getByText('my video')).toBeInTheDocument();
  expect(screen.getByText('1 published')).toBeInTheDocument();
  expect(screen.getByText('other video')).toBeInTheDocument();
  expect(screen.queryByText('0 published')).toBeNull();
});

// SettingsView — platform cookie rows
test('cookie cards render YouTube, Instagram, and TikTok rows with status badges', async () => {
  getConfig.mockResolvedValue(EMPTY_CONFIG);
  cookiesStatus.mockResolvedValue({
    configured: true,
    youtube: true,
    instagram: false,
    tiktok: false,
    legacy: false,
  });
  mount();

  await waitFor(() => expect(screen.getByText('YouTube cookies')).toBeInTheDocument());
  expect(screen.getByText('Instagram cookies')).toBeInTheDocument();
  expect(screen.getByText('TikTok cookies')).toBeInTheDocument();

  // YouTube should show Configurado
  const ytBadge = screen.getByText('YouTube cookies').parentElement.querySelector('.badge');
  expect(ytBadge).toHaveTextContent('Configurado');

  // Instagram should show Não configurado
  const igBadge = screen.getByText('Instagram cookies').parentElement.querySelector('.badge');
  expect(igBadge).toHaveTextContent('Não configurado');

  // Delete button should be present only for configured platforms (YouTube)
  expect(screen.getByRole('button', { name: 'Remove YouTube cookies' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Remove Instagram cookies' })).toBeNull();
});

test('uploading platform cookies calls uploadPlatformCookies and refreshes status', async () => {
  getConfig.mockResolvedValue(EMPTY_CONFIG);
  cookiesStatus
    .mockResolvedValueOnce({ configured: false, youtube: false, instagram: false, tiktok: false, legacy: false })
    .mockResolvedValueOnce({ configured: true, youtube: true, instagram: false, tiktok: false, legacy: false });

  const pushToast = mount();
  await waitFor(() => expect(screen.getByText('YouTube cookies')).toBeInTheDocument());

  const file = new File(['# Netscape HTTP Cookie File\n'], 'youtube.txt', { type: 'text/plain' });
  const uploadLabel = screen.getByLabelText('Upload YouTube cookies');
  const fileInput = uploadLabel.querySelector('input[type="file"]');

  fireEvent.change(fileInput, { target: { files: [file] } });

  await waitFor(() => expect(uploadPlatformCookies).toHaveBeenCalledWith('youtube', file));
  expect(pushToast).toHaveBeenCalledWith('success', 'Youtube cookies uploaded');
});

test('removing platform cookies calls deletePlatformCookies and refreshes status', async () => {
  getConfig.mockResolvedValue(EMPTY_CONFIG);
  cookiesStatus
    .mockResolvedValueOnce({ configured: true, youtube: true, instagram: false, tiktok: false, legacy: false })
    .mockResolvedValueOnce({ configured: false, youtube: false, instagram: false, tiktok: false, legacy: false });

  const pushToast = mount();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Remove YouTube cookies' })).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: 'Remove YouTube cookies' }));

  await waitFor(() => expect(deletePlatformCookies).toHaveBeenCalledWith('youtube'));
  expect(pushToast).toHaveBeenCalledWith('info', 'Youtube cookies removed');
});
