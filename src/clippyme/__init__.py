# Pre-initialize PyTorch runtime before CTranslate2/ONNX Runtime to avoid
# duplicate LLVM CommandLine options registration on ROCm/HIP.
try:
    import torch  # noqa: F401
except ImportError:
    pass
