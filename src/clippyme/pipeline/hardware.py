"""Hardware detection: compute device + auto-selected Whisper model size.

Extracted from ``pipeline.main`` so the shared ``DEVICE`` / ``CUDA_AVAILABLE`` /
``WHISPER_DEVICE`` / ``WHISPER_MODEL`` state lives in one place that both the transcription and
reframe modules can import without a circular dependency on ``main``.
"""
import os
import psutil as _psutil_check

_total_ram_gb = round(_psutil_check.virtual_memory().total / (1024**3), 1)
try:
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
except ImportError:
    DEVICE = "cpu"
    GPU_BACKEND = "CPU"
    CUDA_AVAILABLE = False
    GPU_VRAM_GB = 0.0
    print("ℹ️  PyTorch not installed — using CPU defaults")

def is_local_ai_model(ai_model: str | None) -> bool:
    """Determine whether an AI model identifier refers to a local LLM."""
    if not ai_model:
        return False
    s = str(ai_model).strip().lower()
    if s.startswith(("lmstudio", "lm_studio", "local", "ollama")):
        return True
    if "/" in s and not s.startswith("gemini"):
        return True
    return False


def resolve_whisper_compute(ai_model: str | None = None) -> tuple[str, str]:
    """Dynamically resolve (device, model_name) for Whisper based on the active AI model.

    Rules:
    - User overrides (WHISPER_DEVICE / WHISPER_MODEL env vars) take highest precedence.
    - If local LLM (LM Studio, Ollama): defaults to CPU to protect GPU VRAM.
    - If cloud API (Gemini, Claude, OpenAI): defaults to GPU if available.
    - Model selection scales with VRAM on GPU (large-v3 >= 12GB, medium >= 6GB, small)
      or with system RAM on CPU (medium >= 16GB, small >= 8GB, base).
    """
    env_device = os.getenv("WHISPER_DEVICE")
    env_model = os.getenv("WHISPER_MODEL")

    if env_device:
        device = env_device.strip().lower()
    elif is_local_ai_model(ai_model):
        device = "cpu"
    elif CUDA_AVAILABLE:
        device = "cuda"
    else:
        device = "cpu"

    if env_model:
        model = env_model.strip()
    elif device == "cuda" and CUDA_AVAILABLE:
        if GPU_VRAM_GB >= 12:
            model = "large-v3"
        elif GPU_VRAM_GB >= 6:
            model = "medium"
        else:
            model = "small"
    else:
        if _total_ram_gb >= 16:
            model = "medium"
        elif _total_ram_gb >= 8:
            model = "small"
        else:
            model = "base"

    return device, model


# Default system-wide fallback resolution (without specific AI model context)
WHISPER_DEVICE, WHISPER_MODEL = resolve_whisper_compute(None)
print(
    f"🎙️  Whisper default: {WHISPER_MODEL} on {WHISPER_DEVICE.upper()} "
    f"(auto-selected for {'GPU ' + str(GPU_VRAM_GB) + 'GB' if (WHISPER_DEVICE == 'cuda' and CUDA_AVAILABLE) else 'CPU ' + str(_total_ram_gb) + 'GB RAM'})"
)

