import os

# Pre-initialize PyTorch runtime when needed, unless running isolated worker
if os.getenv("CLIPPYME_NO_TORCH_PREINIT") != "1":
    try:
        import torch  # noqa: F401
    except ImportError:
        pass
