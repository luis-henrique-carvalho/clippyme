"""Whisper transcription module supporting both OpenAI-Whisper (PyTorch ROCm/CUDA) and Faster-Whisper.

Runs Whisper transcription cleanly and safely with isolated execution support, preventing
memory allocator collisions and supporting native GPU acceleration on AMD ROCm/HIP and NVIDIA CUDA.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("clippyme")


def _transcribe_openai_whisper(
    audio_path: str,
    model_name: str = "medium",
    device: str = "cuda",
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute transcription using OpenAI-Whisper (PyTorch ROCm/CUDA/CPU)."""
    import torch
    import whisper

    use_fp16 = device == "cuda" and torch.cuda.is_available()
    model = whisper.load_model(model_name, device=device)

    kwargs: Dict[str, Any] = {
        "word_timestamps": True,
        "fp16": use_fp16,
    }
    if language and language != "None":
        kwargs["language"] = language

    result = model.transcribe(audio_path, **kwargs)

    transcript_segments = []
    raw_segments = result.get("segments") or []

    for s in raw_segments:
        words = []
        raw_words = s.get("words") or []
        if raw_words:
            for w in raw_words:
                words.append({
                    "word": str(w.get("word", "")),
                    "start": float(w.get("start", 0.0)),
                    "end": float(w.get("end", 0.0)),
                    "probability": float(w.get("probability", 1.0)),
                })
        else:
            seg_text = str(s.get("text", "")).strip()
            if seg_text:
                tokens = seg_text.split()
                s_start = float(s.get("start", 0.0))
                s_end = float(s.get("end", 0.0))
                duration = max(0.01, s_end - s_start)
                step = duration / max(1, len(tokens))
                for i, tok in enumerate(tokens):
                    w_start = s_start + i * step
                    w_end = s_start + (i + 1) * step if i < len(tokens) - 1 else s_end
                    words.append({
                        "word": tok,
                        "start": round(w_start, 3),
                        "end": round(w_end, 3),
                        "probability": 1.0,
                    })

        transcript_segments.append({
            "text": str(s.get("text", "")),
            "start": float(s.get("start", 0.0)),
            "end": float(s.get("end", 0.0)),
            "words": words,
        })

    return {
        "text": str(result.get("text", "")).strip(),
        "segments": transcript_segments,
        "language": str(result.get("language", "en")),
        "probability": float(result.get("language_probability", 1.0)) if "language_probability" in result else 1.0,
    }


def _transcribe_faster_whisper(
    audio_path: str,
    model_name: str = "medium",
    device: str = "cpu",
    compute_type: str = "default",
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute transcription using Faster-Whisper (CTranslate2)."""
    from faster_whisper import WhisperModel

    if device == "cpu" and compute_type == "float16":
        compute_type = "default"

    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as exc:
        if compute_type != "default":
            logger.warning(
                "Failed to initialize Faster-Whisper with compute_type=%s (%s), falling back to 'default'",
                compute_type,
                exc,
            )
            model = WhisperModel(model_name, device=device, compute_type="default")
        else:
            raise exc

    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        language=language if language and language != "None" else None,
    )

    transcript_segments = []
    full_text = ""

    for s in segments:
        words = []
        if s.words:
            for w in s.words:
                words.append({
                    "word": str(w.word),
                    "start": float(w.start),
                    "end": float(w.end),
                    "probability": float(getattr(w, "probability", 1.0)),
                })
        else:
            seg_text = str(s.text).strip()
            if seg_text:
                tokens = seg_text.split()
                s_start = float(s.start)
                s_end = float(s.end)
                duration = max(0.01, s_end - s_start)
                step = duration / max(1, len(tokens))
                for i, tok in enumerate(tokens):
                    w_start = s_start + i * step
                    w_end = s_start + (i + 1) * step if i < len(tokens) - 1 else s_end
                    words.append({
                        "word": tok,
                        "start": round(w_start, 3),
                        "end": round(w_end, 3),
                        "probability": 1.0,
                    })

        transcript_segments.append({
            "text": str(s.text),
            "start": float(s.start),
            "end": float(s.end),
            "words": words,
        })
        full_text += s.text + " "

    return {
        "text": full_text.strip(),
        "segments": transcript_segments,
        "language": str(getattr(info, "language", "en")),
        "probability": float(getattr(info, "language_probability", 1.0)),
    }


def transcribe_audio_direct(
    audio_path: str,
    model_name: str = "medium",
    device: str = "cpu",
    compute_type: str = "default",
    language: Optional[str] = None,
    engine: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute Whisper transcription in the current process.

    Engine selection:
        - "openai-whisper": PyTorch ROCm / CUDA / CPU backend
        - "faster-whisper": CTranslate2 backend
        - "auto" / None:
            - device == "cuda": PyTorch openai-whisper (native AMD ROCm/HIP and NVIDIA CUDA)
            - device == "cpu": faster-whisper with automatic fallback to openai-whisper
    """
    selected_engine = (engine or os.getenv("WHISPER_ENGINE") or "auto").strip().lower()

    if selected_engine == "auto":
        if device == "cuda":
            selected_engine = "openai-whisper"
        else:
            selected_engine = "faster-whisper"

    if selected_engine == "openai-whisper":
        try:
            return _transcribe_openai_whisper(
                audio_path=audio_path,
                model_name=model_name,
                device=device,
                language=language,
            )
        except Exception as exc:
            logger.warning("openai-whisper failed (%s), falling back...", exc)
            if device != "cpu":
                try:
                    return _transcribe_openai_whisper(
                        audio_path=audio_path,
                        model_name="small" if model_name in ("large-v3", "large") else model_name,
                        device="cpu",
                        language=language,
                    )
                except Exception as exc_cpu:
                    logger.warning("openai-whisper CPU fallback failed (%s), falling back to faster-whisper", exc_cpu)
                    return _transcribe_faster_whisper(
                        audio_path=audio_path,
                        model_name=model_name,
                        device="cpu",
                        compute_type="default",
                        language=language,
                    )
            else:
                return _transcribe_faster_whisper(
                    audio_path=audio_path,
                    model_name=model_name,
                    device="cpu",
                    compute_type="default",
                    language=language,
                )
    else:
        try:
            return _transcribe_faster_whisper(
                audio_path=audio_path,
                model_name=model_name,
                device=device,
                compute_type=compute_type,
                language=language,
            )
        except Exception as exc:
            logger.warning("faster-whisper failed (%s), falling back to openai-whisper", exc)
            try:
                return _transcribe_openai_whisper(
                    audio_path=audio_path,
                    model_name=model_name,
                    device=device,
                    language=language,
                )
            except Exception as exc2:
                if device != "cpu":
                    logger.warning("GPU transcription failed (%s, %s); falling back to CPU", exc, exc2)
                    return _transcribe_openai_whisper(
                        audio_path=audio_path,
                        model_name="small" if model_name in ("large-v3", "large") else model_name,
                        device="cpu",
                        language=language,
                    )
                raise exc2


def transcribe_with_whisper(
    audio_path: str,
    model_name: str = "medium",
    device: str = "cpu",
    compute_type: str = "default",
    language: Optional[str] = None,
    engine: Optional[str] = None,
) -> Dict[str, Any]:
    """Transcribe audio using Whisper via an isolated CLI worker."""
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    cmd = [
        sys.executable,
        "-m",
        "clippyme.pipeline.whisper_transcribe",
        "--audio",
        audio_path,
        "--model",
        model_name,
        "--device",
        device,
        "--compute-type",
        compute_type,
    ]
    if language and language != "None":
        cmd.extend(["--language", language])
    if engine and engine != "None":
        cmd.extend(["--engine", engine])

    worker_env = dict(os.environ)
    worker_env["CLIPPYME_NO_TORCH_PREINIT"] = "1"

    proc = subprocess.run(
        cmd,
        env=worker_env,
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode != 0:
        logger.error("Whisper worker failed (code %s): %s", proc.returncode, proc.stderr)
        raise RuntimeError(
            f"Whisper transcription failed: {proc.stderr.strip() or 'Exit code ' + str(proc.returncode)}"
        )

    marker = "###WHISPER_OUTPUT_START###"
    if marker not in proc.stdout:
        logger.error("Marker not found in whisper stdout: %s", proc.stdout)
        raise RuntimeError("Malformed whisper worker output")

    raw_json = proc.stdout.split(marker, 1)[1].strip()
    return json.loads(raw_json)


# Backwards compatibility alias
transcribe_with_faster_whisper = transcribe_with_whisper


def _cli_entrypoint():
    """CLI entrypoint used by the isolated subprocess worker."""
    parser = argparse.ArgumentParser(description="ClippyMe Whisper isolated worker")
    parser.add_argument("--audio", required=True, help="Path to audio file")
    parser.add_argument("--model", default="medium", help="Whisper model name")
    parser.add_argument("--device", default="cpu", help="Device (cpu/cuda)")
    parser.add_argument("--compute-type", default="default", help="Compute type")
    parser.add_argument("--language", default=None, help="Language code")
    parser.add_argument("--engine", default=None, help="Engine (auto/openai-whisper/faster-whisper)")
    args = parser.parse_args()

    result = transcribe_audio_direct(
        audio_path=args.audio,
        model_name=args.model,
        device=args.device,
        compute_type=args.compute_type,
        language=args.language,
        engine=args.engine,
    )
    print("###WHISPER_OUTPUT_START###" + json.dumps(result))


if __name__ == "__main__":
    _cli_entrypoint()
