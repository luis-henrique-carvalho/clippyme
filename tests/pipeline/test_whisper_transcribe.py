"""Tests for clippyme.pipeline.whisper_transcribe and hardware detection."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from clippyme.pipeline import hardware
from clippyme.pipeline import whisper_transcribe as wt


def test_hardware_constants_defined():
    """Verify hardware module exports valid configuration constants."""
    assert hasattr(hardware, "DEVICE")
    assert hardware.DEVICE in ("cuda", "cpu")
    assert hasattr(hardware, "CUDA_AVAILABLE")
    assert isinstance(hardware.CUDA_AVAILABLE, bool)
    assert hasattr(hardware, "GPU_BACKEND")
    assert hardware.GPU_BACKEND in ("ROCm/HIP", "CUDA", "CPU")
    assert hasattr(hardware, "WHISPER_DEVICE")
    assert hardware.WHISPER_DEVICE in ("cuda", "cpu")
    assert hasattr(hardware, "WHISPER_MODEL")
    assert isinstance(hardware.WHISPER_MODEL, str)


def test_transcribe_missing_file_raises_not_found(tmp_path):
    """transcribe_with_whisper must raise FileNotFoundError for non-existent files."""
    missing = str(tmp_path / "does_not_exist.wav")
    with pytest.raises(FileNotFoundError):
        wt.transcribe_with_whisper(missing)


def test_openai_whisper_formatting(monkeypatch):
    """_transcribe_openai_whisper should properly cast and structure segments and words."""
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {
        "text": "  hello world  ",
        "language": "en",
        "language_probability": 0.98,
        "segments": [
            {
                "text": " hello world",
                "start": 0.0,
                "end": 2.5,
                "words": [
                    {"word": " hello", "start": 0.0, "end": 1.0, "probability": 0.99},
                    {"word": " world", "start": 1.0, "end": 2.5, "probability": 0.97},
                ],
            }
        ],
    }

    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False

    with patch.dict("sys.modules", {"whisper": mock_whisper, "torch": mock_torch}):
        res = wt._transcribe_openai_whisper("dummy.wav", model_name="tiny", device="cpu")

    assert res["text"] == "hello world"
    assert res["language"] == "en"
    assert res["probability"] == 0.98
    assert len(res["segments"]) == 1
    assert res["segments"][0]["start"] == 0.0
    assert res["segments"][0]["end"] == 2.5
    assert len(res["segments"][0]["words"]) == 2
    assert res["segments"][0]["words"][0]["word"] == " hello"


def test_transcribe_audio_direct_engine_auto_routing(monkeypatch):
    """transcribe_audio_direct in auto mode should select openai-whisper on cuda."""
    mock_transcribe = MagicMock(return_value={"text": "ok", "segments": [], "language": "en", "probability": 1.0})
    monkeypatch.setattr(wt, "_transcribe_openai_whisper", mock_transcribe)

    res = wt.transcribe_audio_direct("dummy.wav", model_name="tiny", device="cuda", engine="auto")
    assert res["text"] == "ok"
    assert mock_transcribe.called


def test_transcribe_audio_direct_fallback(monkeypatch):
    """transcribe_audio_direct should fallback to secondary engine if primary raises."""
    mock_openai = MagicMock(side_effect=RuntimeError("Primary engine failed"))
    mock_faster = MagicMock(return_value={"text": "fallback_ok", "segments": [], "language": "en", "probability": 1.0})

    monkeypatch.setattr(wt, "_transcribe_openai_whisper", mock_openai)
    monkeypatch.setattr(wt, "_transcribe_faster_whisper", mock_faster)

    res = wt.transcribe_audio_direct("dummy.wav", model_name="tiny", device="cuda", engine="openai-whisper")
    assert res["text"] == "fallback_ok"
    assert mock_openai.called
    assert mock_faster.called


def test_transcribe_audio_direct_gpu_to_cpu_fallback(monkeypatch):
    """transcribe_audio_direct should fall back to CPU when both GPU attempts fail."""
    def side_effect(audio_path, model_name="medium", device="cpu", **kwargs):
        if device == "cuda":
            raise RuntimeError("CUDA OOM / crash")
        return {"text": "cpu_recovery", "segments": [], "language": "en", "probability": 1.0}

    mock_openai = MagicMock(side_effect=side_effect)
    mock_faster = MagicMock(side_effect=side_effect)

    monkeypatch.setattr(wt, "_transcribe_openai_whisper", mock_openai)
    monkeypatch.setattr(wt, "_transcribe_faster_whisper", mock_faster)

    res = wt.transcribe_audio_direct("dummy.wav", model_name="medium", device="cuda", engine="openai-whisper")
    assert res["text"] == "cpu_recovery"


def test_openai_whisper_synthesizes_words_if_empty(monkeypatch):
    """If whisper outputs a segment without word timestamps, words are synthesized."""
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {
        "text": "quick test",
        "language": "en",
        "segments": [
            {
                "text": "quick test",
                "start": 0.0,
                "end": 2.0,
                "words": [],
            }
        ],
    }
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False

    with patch.dict("sys.modules", {"whisper": mock_whisper, "torch": mock_torch}):
        res = wt._transcribe_openai_whisper("dummy.wav", model_name="tiny", device="cpu")

    assert len(res["segments"]) == 1
    assert len(res["segments"][0]["words"]) == 2
    assert res["segments"][0]["words"][0]["word"] == "quick"
    assert res["segments"][0]["words"][1]["word"] == "test"


def test_is_local_ai_model():
    """Verify local AI model recognition logic."""
    assert hardware.is_local_ai_model("lmstudio:qwen2.5-coder-7b") is True
    assert hardware.is_local_ai_model("ollama:llama3") is True
    assert hardware.is_local_ai_model("local:mistral") is True
    assert hardware.is_local_ai_model("google/gemma-4-12b-qat") is True

    assert hardware.is_local_ai_model("gemini-2.5-flash") is False
    assert hardware.is_local_ai_model("gemini:gemini-1.5-pro") is False
    assert hardware.is_local_ai_model("openai:gpt-4o") is False
    assert hardware.is_local_ai_model("claude-3-5-sonnet") is False
    assert hardware.is_local_ai_model("") is False
    assert hardware.is_local_ai_model(None) is False


def test_resolve_whisper_compute_local_ai_routes_to_cpu(monkeypatch):
    """When using local AI models, resolve_whisper_compute must route to CPU."""
    monkeypatch.delenv("WHISPER_DEVICE", raising=False)
    monkeypatch.delenv("WHISPER_MODEL", raising=False)

    device, model = hardware.resolve_whisper_compute(ai_model="lmstudio:google/gemma-4-12b-qat")
    assert device == "cpu"
    assert model in ("large-v3", "medium", "small", "base")


def test_resolve_whisper_compute_cloud_ai_routes_to_gpu_if_available(monkeypatch):
    """When using cloud AI models, resolve_whisper_compute routes to GPU if CUDA/ROCm is available."""
    monkeypatch.delenv("WHISPER_DEVICE", raising=False)
    monkeypatch.delenv("WHISPER_MODEL", raising=False)

    monkeypatch.setattr(hardware, "CUDA_AVAILABLE", True)
    monkeypatch.setattr(hardware, "GPU_VRAM_GB", 16.0)

    device, model = hardware.resolve_whisper_compute(ai_model="gemini-2.5-flash")
    assert device == "cuda"
    assert model == "large-v3"

