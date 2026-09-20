"""Unit tests for multi-signal context extraction in Viral Content Studio."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clippyme.domain.viral_studio_context import (
    VideoContext,
    _detect_scene_timestamps,
    _extract_audio_transcript,
    _extract_frame_jpeg,
    _probe_duration,
    extract_viral_context,
)


def test_video_context_summary_dict():
    """VideoContext.to_summary_dict formats compact observability dict."""
    ctx = VideoContext(
        keyframes=[b"frame1", b"frame2"],
        transcript="Olha esse produto incrível para sua cozinha",
        original_caption="Melhor achadinho da Shopee! #cozinha",
        title="Mini Selador Portátil",
        tags=["#cozinha", "#shopee"],
        scenes_count=3,
        has_audio=True,
        duration=15.54,
    )
    summary = ctx.to_summary_dict()
    assert summary["scenes_count"] == 3
    assert summary["keyframes_count"] == 2
    assert summary["has_audio"] is True
    assert summary["transcript_words"] == 7
    assert summary["has_original_caption"] is True
    assert summary["duration"] == 15.54


def test_probe_duration_with_mock_ffprobe(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_bytes(b"dummy")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "24.50\n"

    with patch("subprocess.run", return_value=mock_proc):
        dur = _probe_duration(str(video))
        assert dur == 24.50


def test_probe_duration_missing_file():
    dur = _probe_duration("/nonexistent/video.mp4")
    assert dur == 0.0


def test_detect_scene_timestamps_pyscenedetect_fallback():
    """When PySceneDetect is unavailable or raises, falls back to temporal milestone sampling."""
    timestamps, scenes = _detect_scene_timestamps("dummy.mp4", duration=20.0, max_scenes=4)
    assert len(timestamps) == 3
    assert timestamps == [4.0, 10.0, 16.0]
    assert scenes == 1


def test_extract_frame_jpeg_ffmpeg_success(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_bytes(b"dummy")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = b"\xff\xd8\xff\xe0" + b"\x00" * 200  # Valid JPEG header + payload

    with patch("subprocess.run", return_value=mock_proc):
        frame = _extract_frame_jpeg(str(video), timestamp=2.5, max_dimension=512)
        assert frame is not None
        assert len(frame) > 100


def test_extract_audio_transcript_speech_list():
    """Extracts text from segments list."""
    segments = [
        {"text": "Economize tempo", "start": 0.0, "end": 2.0},
        {"text": "com este selador térmico!", "start": 2.0, "end": 4.5},
    ]
    mock_mod = MagicMock()
    mock_mod.transcribe_video.return_value = segments

    with patch("importlib.import_module", return_value=mock_mod):
        transcript = _extract_audio_transcript("dummy.mp4")
        assert transcript == "Economize tempo com este selador térmico!"


def test_extract_audio_transcript_empty_or_failure():
    """Gracefully returns empty string if audio transcription fails or has no speech."""
    with patch("importlib.import_module", side_effect=ImportError("No transcriber")):
        transcript = _extract_audio_transcript("dummy.mp4")
        assert transcript == ""


def test_extract_viral_context_full_pipeline(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"dummy video data")

    source_meta = {
        "title": "Aspirador Portátil Sem Fio",
        "description": "Limpa tudo em segundos! Link na bio #achadinhos",
        "tags": ["#achadinhos", "#limpeza"],
    }

    with patch("clippyme.domain.viral_studio_context._probe_duration", return_value=12.0), \
         patch("clippyme.domain.viral_studio_context._detect_scene_timestamps", return_value=([2.4, 6.0, 9.6], 3)), \
         patch("clippyme.domain.viral_studio_context._extract_frame_jpeg", return_value=b"fake_jpeg_bytes"), \
         patch("clippyme.domain.viral_studio_context._extract_audio_transcript", return_value="Aspirador muito potente e leve"):

        ctx = extract_viral_context(str(video), source_metadata=source_meta, max_frames=3)

        assert ctx.duration == 12.0
        assert ctx.scenes_count == 3
        assert len(ctx.keyframes) == 3
        assert ctx.has_audio is True
        assert "Aspirador" in ctx.transcript
        assert ctx.title == "Aspirador Portátil Sem Fio"
        assert "Limpa tudo" in ctx.original_caption
        assert "#achadinhos" in ctx.tags


def test_video_context_summary_preserves_has_audio_flag():
    """VideoContext summary preserves has_audio=True even if transcript is empty (e.g. music-only or non-speech audio)."""
    ctx = VideoContext(
        keyframes=[],
        transcript="",
        has_audio=True,
        duration=5.0,
    )
    summary = ctx.to_summary_dict()
    assert summary["has_audio"] is True
    assert summary["transcript_words"] == 0


def test_extract_audio_transcript_dict_formats():
    """Extracts text when transcriber returns dict with text or segments."""
    mock_mod = MagicMock()
    mock_mod.transcribe_video.return_value = {
        "segments": [
            {"text": "Primeira frase."},
            {"text": "Segunda frase."},
        ]
    }
    with patch("importlib.import_module", return_value=mock_mod):
        res = _extract_audio_transcript("dummy.mp4")
        assert res == "Primeira frase. Segunda frase."

    mock_mod.transcribe_video.return_value = {"text": "Texto completo direto"}
    with patch("importlib.import_module", return_value=mock_mod):
        res = _extract_audio_transcript("dummy.mp4")
        assert res == "Texto completo direto"

