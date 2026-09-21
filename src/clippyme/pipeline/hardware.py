"""Hardware detection: compute device + auto-selected Whisper model size.

Extracted from ``pipeline.main`` so the shared ``DEVICE`` / ``CUDA_AVAILABLE`` /
``WHISPER_DEVICE`` / ``WHISPER_MODEL`` state lives in one place that both the transcription and
reframe modules can import without a circular dependency on ``main``.
"""
import os
import psutil as _psutil_check
import torch

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
GPU_BACKEND = "ROCm/HIP" if getattr(torch.version, "hip", None) else "CUDA"
CUDA_AVAILABLE = bool(torch.cuda.is_available())
GPU_VRAM_GB = 0.0

if CUDA_AVAILABLE:
    try:
        GPU_VRAM_GB = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 1)
        print(f"✅ {GPU_BACKEND} GPU detected — {torch.cuda.get_device_name(0)} ({GPU_VRAM_GB}GB VRAM)")
    except Exception as e:
        CUDA_AVAILABLE = False
        print(f"⚠️  {GPU_BACKEND} GPU detection failed: {e} — using CPU")
else:
    print(f"ℹ️  No {GPU_BACKEND} GPU detected — using CPU")

# Whisper device: defaults to CPU to leave 100% of GPU VRAM for LLM & vision workloads
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu").strip().lower()

# Auto-select Whisper model based on available hardware
# Models: tiny (39M) < base (74M) < small (244M) < medium (769M) < large-v3 (1.55B)
_total_ram_gb = round(_psutil_check.virtual_memory().total / (1024**3), 1)

if WHISPER_DEVICE == "cuda" and CUDA_AVAILABLE:
    if GPU_VRAM_GB >= 8:
        WHISPER_MODEL = "medium"
    else:
        WHISPER_MODEL = "small"
else:
    if _total_ram_gb >= 16:
        WHISPER_MODEL = "medium"
    elif _total_ram_gb >= 8:
        WHISPER_MODEL = "small"
    else:
        WHISPER_MODEL = "base"

# Allow override via env var
WHISPER_MODEL = os.getenv("WHISPER_MODEL", WHISPER_MODEL)
print(
    f"🎙️  Whisper model: {WHISPER_MODEL} on {WHISPER_DEVICE.upper()} "
    f"(auto-selected for {'GPU ' + str(GPU_VRAM_GB) + 'GB' if (WHISPER_DEVICE == 'cuda' and CUDA_AVAILABLE) else 'CPU ' + str(_total_ram_gb) + 'GB RAM'})"
)
