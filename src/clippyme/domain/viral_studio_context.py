"""Context extraction for Viral Content Studio.

Extracts multi-signal video context:
1. Source metadata (original post description, title, hashtags from yt-dlp).
2. Keyframes (JPEG images from PySceneDetect scene changes or temporal milestones).
3. Audio transcription (speech-to-text from configured provider / Whisper).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, List, Optional

from clippyme.domain.viral_studio_download import get_source_manifest

logger = logging.getLogger("clippyme.viral_studio_context")


@dataclass
class VideoContext:
    """Multi-signal contextual analysis of a viral video item."""

    keyframes: List[bytes] = field(default_factory=list)
    keyframe_urls: List[str] = field(default_factory=list)
    keyframe_paths: List[str] = field(default_factory=list)
    transcript: str = ""
    original_caption: str = ""
    title: str = ""
    tags: List[str] = field(default_factory=list)
    uploader: str = ""
    scenes_count: int = 0
    has_audio: bool = False
    duration: float = 0.0

    def to_summary_dict(self) -> dict[str, Any]:
        """Compact summary dict to persist in item['ai_context_summary']."""
        return {
            "scenes_count": self.scenes_count,
            "keyframes_count": len(self.keyframes),
            "keyframe_urls": self.keyframe_urls,
            "has_audio": bool(self.has_audio or (self.transcript and self.transcript.strip())),
            "transcript": self.transcript,
            "transcript_words": len(self.transcript.split()) if self.transcript else 0,
            "has_original_caption": bool(self.original_caption and self.original_caption.strip()),
            "original_caption": self.original_caption,
            "title": self.title,
            "tags": self.tags,
            "uploader": self.uploader,
            "duration": round(self.duration, 2),
        }


def _probe_duration(video_path: str) -> float:
    """Probe duration in seconds using ffprobe or fallback."""
    if not os.path.isfile(video_path):
        return 0.0
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return max(0.0, float(result.stdout.strip()))
    except Exception as exc:
        logger.debug("ffprobe duration probe failed: %s", exc)

    # Secondary fallback via cv2 if available
    try:
        import cv2

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        if fps and fps > 0 and count > 0:
            return float(count / fps)
    except Exception:
        pass

    return 0.0


def _detect_scene_timestamps(video_path: str, duration: float, max_scenes: int = 4) -> tuple[list[float], int]:
    """Identify key timestamps from scene cuts using PySceneDetect, with temporal fallback."""
    scenes_count = 0
    timestamps: list[float] = []

    # Attempt PySceneDetect
    try:
        from clippyme.pipeline.scene_detection import detect_scenes

        scene_list, _fps = detect_scenes(video_path)
        if scene_list:
            scenes_count = len(scene_list)
            for scene in scene_list[:max_scenes]:
                # scene is (start_time, end_time)
                start_sec = scene[0].get_seconds()
                end_sec = scene[1].get_seconds()
                mid = (start_sec + end_sec) / 2.0
                timestamps.append(mid)
    except Exception as exc:
        logger.debug("Scene detection unavailable or failed: %s", exc)

    # Fallback if no scenes detected or PySceneDetect unavailable
    if not timestamps:
        dur = duration if duration > 0 else 10.0
        # Sample at 20%, 50%, 80% of video
        timestamps = [dur * 0.20, dur * 0.50, dur * 0.80]
        if scenes_count == 0:
            scenes_count = 1

    # Ensure unique and sorted timestamps
    clean_timestamps = sorted(list({round(t, 2) for t in timestamps if t >= 0}))
    return clean_timestamps[:max_scenes], scenes_count


def _extract_frame_jpeg(video_path: str, timestamp: float, max_dimension: int = 512) -> Optional[bytes]:
    """Extract a single frame at timestamp as a downscaled JPEG byte buffer."""
    # Method 1: ffmpeg subprocess (fast and clean)
    try:
        scale_filter = f"scale='if(gt(iw,ih),{max_dimension},-2)':'if(gt(iw,ih),-2,{max_dimension})'"
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            video_path,
            "-vf",
            scale_filter,
            "-vframes",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-q:v",
            "4",
            "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=10)
        if proc.returncode == 0 and len(proc.stdout) > 100:
            return proc.stdout
    except Exception as exc:
        logger.debug("ffmpeg frame extraction failed at %ss: %s", timestamp, exc)

    # Method 2: OpenCV fallback if ffmpeg is unavailable
    try:
        import cv2

        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        success, frame = cap.read()
        cap.release()
        if success and frame is not None:
            h, w = frame.shape[:2]
            if max(h, w) > max_dimension:
                scale = max_dimension / max(h, w)
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            success, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if success:
                return enc.tobytes()
    except Exception as exc:
        logger.debug("cv2 frame extraction failed at %ss: %s", timestamp, exc)

    return None


def _extract_audio_transcript(video_path: str) -> str:
    """Transcribe video audio using ClippyMe transcription pipeline."""
    try:
        import importlib

        main_mod = importlib.import_module("clippyme.pipeline.main")
        transcribe_fn = getattr(main_mod, "transcribe_video", None)
        if transcribe_fn:
            transcript_data = transcribe_fn(video_path)
            if isinstance(transcript_data, list):
                lines = []
                for item in transcript_data:
                    if isinstance(item, dict):
                        if "text" in item:
                            lines.append(str(item["text"]).strip())
                        elif "word" in item:
                            lines.append(str(item["word"]).strip())
                    elif isinstance(item, str):
                        lines.append(item.strip())
                return " ".join([l for l in lines if l])
            elif isinstance(transcript_data, str):
                return transcript_data.strip()
            elif isinstance(transcript_data, dict):
                if "text" in transcript_data and isinstance(transcript_data["text"], str):
                    return transcript_data["text"].strip()
                if "transcript" in transcript_data and isinstance(transcript_data["transcript"], str):
                    return transcript_data["transcript"].strip()
                if "segments" in transcript_data and isinstance(transcript_data["segments"], list):
                    lines = [str(s.get("text", "")).strip() for s in transcript_data["segments"] if isinstance(s, dict)]
                    return " ".join([l for l in lines if l])
    except Exception as exc:
        logger.debug("Audio transcription not available or returned empty: %s", exc)
    return ""


def extract_viral_context(
    video_path: str,
    source_metadata: Optional[dict[str, Any]] = None,
    max_frames: int = 4,
    keyframes_dir: Optional[str] = None,
    batch_id: Optional[str] = None,
    item_id: Optional[str] = None,
) -> VideoContext:
    """Extract complete multi-signal context from a video file."""
    if not video_path or not os.path.isfile(video_path):
        return VideoContext()

    duration = _probe_duration(video_path)

    # Resolve post metadata from manifest or parameter
    meta = dict(source_metadata or {})
    if not meta:
        manifest = get_source_manifest(video_path)
        meta = manifest.get("metadata") or {}

    original_caption = meta.get("description") or meta.get("caption") or ""
    title = meta.get("title") or ""
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    uploader = meta.get("uploader") or meta.get("channel") or meta.get("author") or meta.get("creator") or ""

    # Resolve keyframes destination directory
    target_kf_dir = keyframes_dir
    if not target_kf_dir and batch_id and item_id:
        out_dir = os.environ.get("CLIPPYME_OUTPUT_DIR") or "output"
        target_kf_dir = os.path.join(out_dir, "viral_studio", batch_id, item_id, "keyframes")

    if target_kf_dir:
        try:
            os.makedirs(target_kf_dir, exist_ok=True)
        except Exception as exc:
            logger.debug("Could not create keyframes directory %s: %s", target_kf_dir, exc)

    # Extract scene timestamps & keyframe images
    timestamps, scenes_count = _detect_scene_timestamps(video_path, duration, max_scenes=max_frames)
    keyframes: list[bytes] = []
    keyframe_paths: list[str] = []
    keyframe_urls: list[str] = []

    for i, ts in enumerate(timestamps):
        frame_bytes = _extract_frame_jpeg(video_path, ts)
        if frame_bytes:
            keyframes.append(frame_bytes)
            if target_kf_dir and os.path.isdir(target_kf_dir):
                kf_filename = f"scene_{i}.jpg"
                kf_path = os.path.join(target_kf_dir, kf_filename)
                try:
                    with open(kf_path, "wb") as f:
                        f.write(frame_bytes)
                    keyframe_paths.append(kf_path)
                    if batch_id and item_id:
                        keyframe_urls.append(f"/videos/viral_studio/{batch_id}/{item_id}/keyframes/{kf_filename}")
                    else:
                        out_dir = os.environ.get("CLIPPYME_OUTPUT_DIR") or "output"
                        try:
                            rel = os.path.relpath(kf_path, out_dir).replace(os.sep, "/")
                            keyframe_urls.append(f"/videos/{rel}")
                        except Exception:
                            keyframe_urls.append(f"/videos/viral_studio/default/item/keyframes/{kf_filename}")
                except Exception as exc:
                    logger.debug("Could not write keyframe file %s: %s", kf_path, exc)

    # Extract speech / audio transcript
    transcript = _extract_audio_transcript(video_path)

    return VideoContext(
        keyframes=keyframes,
        keyframe_urls=keyframe_urls,
        keyframe_paths=keyframe_paths,
        transcript=transcript,
        original_caption=original_caption,
        title=title,
        tags=tags,
        uploader=uploader,
        scenes_count=scenes_count,
        has_audio=bool(transcript.strip()),
        duration=duration,
    )
