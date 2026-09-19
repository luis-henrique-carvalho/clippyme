"""Visual Template Rendering Engine for Viral Content Studio (Milestone 4).

Composes a 1080x1920 (9:16 vertical) affiliate video from:
1. Brand header overlay (circular avatar, brand name, handle).
2. Dynamic multiline headline positioned above video with auto-downscaling.
3. Contain-fit source video preserving aspect ratio with no stretching or distortion.
4. Original audio stream copy (-c:a copy with AAC fallback).
5. Optional brand logo watermark overlay with configurable position and opacity.
6. Standardized encoding parameters via ``x264_video_args()``.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageFont

from clippyme.api.viral_studio_schemas import Brand, VisualTemplate
from clippyme.domain.encode import ffmpeg_timeout, x264_video_args
from clippyme.domain.errors import ComposeError
from clippyme.domain.logo import DEFAULT_POSITION, logo_filter_chain

logger = logging.getLogger("clippyme.viral_studio_renderer")

# Locate fonts directory
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)
FONTS_DIR = os.environ.get("CLIPPYME_FONTS_DIR") or os.path.join(_REPO_ROOT, "fonts")
if not os.path.isdir(FONTS_DIR):
    _cwd_fallback = os.path.abspath("fonts")
    if os.path.isdir(_cwd_fallback):
        FONTS_DIR = _cwd_fallback

DEFAULT_HEADLINE_FONT = "Montserrat-ExtraBold.ttf"
DEFAULT_BRAND_FONT = "Montserrat-ExtraBold.ttf"
DEFAULT_HANDLE_FONT = "Poppins-Medium.ttf"

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _extract_field(obj: Any, field_name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(field_name, default)
    return getattr(obj, field_name, default)


def _hex_to_rgba(hex_str: str, alpha: int = 255, default: Tuple[int, int, int] = (0, 0, 0)) -> Tuple[int, int, int, int]:
    """Convert hex color (#RRGGBB) to (r, g, b, alpha) tuple."""
    if isinstance(hex_str, str):
        clean = hex_str.strip()
        if clean.startswith("#") and len(clean) == 7:
            try:
                r = int(clean[1:3], 16)
                g = int(clean[3:5], 16)
                b = int(clean[5:7], 16)
                return (r, g, b, int(alpha))
            except ValueError:
                pass
    return (*default, int(alpha))


def _hex_to_ffmpeg_color(hex_str: str, default: str = "0xFFFFFF") -> str:
    """Format hex color for FFmpeg filter parameter (e.g. 0xFFFFFF)."""
    if isinstance(hex_str, str):
        clean = hex_str.strip().lstrip("#")
        if len(clean) == 6:
            return f"0x{clean.upper()}"
    return default


def _resolve_font(font_filename: str, size: int) -> ImageFont.ImageFont:
    """Resolve a TrueType font from bundled fonts or system, fallback to default."""
    if font_filename:
        candidates = [
            os.path.join(FONTS_DIR, font_filename),
            os.path.join(FONTS_DIR, f"{font_filename}.ttf"),
            font_filename,
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                try:
                    return ImageFont.truetype(candidate, size)
                except Exception:
                    pass

    # Try standard bundled fonts
    for fallback_name in (
        "Montserrat-ExtraBold.ttf",
        "NotoSerif-Bold.ttf",
        "Poppins-Medium.ttf",
        "Anton-Regular.ttf",
    ):
        fallback_path = os.path.join(FONTS_DIR, fallback_name)
        if os.path.isfile(fallback_path):
            try:
                return ImageFont.truetype(fallback_path, size)
            except Exception:
                pass

    try:
        return ImageFont.load_default()
    except Exception:
        return None  # type: ignore


def wrap_and_fit_headline(
    text: str,
    max_width: int,
    max_lines: int,
    base_font_size: int = 48,
    min_font_size: int = 24,
    font_name: str = DEFAULT_HEADLINE_FONT,
) -> Tuple[List[str], int, int]:
    """Wrap headline text into lines with auto-downscaling to fit max_lines. Pure function.

    Returns:
        (lines, final_font_size, total_text_height)
    """
    clean_text = " ".join((text or "").strip().split())
    if not clean_text:
        return ([], base_font_size, 0)

    words = clean_text.split()
    dummy_img = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy_img)

    current_size = base_font_size
    best_lines: List[str] = []
    line_spacing_ratio = 0.20

    while current_size >= min_font_size:
        font = _resolve_font(font_name, current_size)
        lines: List[str] = []
        current_line: List[str] = []

        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_w = bbox[2] - bbox[0]

            if line_w <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    # Single word is wider than max_width
                    lines.append(word)
                    current_line = []

        if current_line:
            lines.append(" ".join(current_line))

        if len(lines) <= max_lines:
            best_lines = lines
            break
        else:
            best_lines = lines
            current_size -= 2

    # If still exceeding max_lines at min_font_size, truncate last line with ellipsis
    if len(best_lines) > max_lines:
        font = _resolve_font(font_name, current_size)
        trimmed_lines = best_lines[: max_lines - 1]
        overflow_words = " ".join(best_lines[max_lines - 1 :])
        # Find truncation point with "..."
        truncated = overflow_words
        while truncated and draw.textbbox((0, 0), f"{truncated}...", font=font)[2] - draw.textbbox((0, 0), f"{truncated}...", font=font)[0] > max_width:
            truncated = " ".join(truncated.split()[:-1])
        trimmed_lines.append(f"{truncated}..." if truncated else "...")
        best_lines = trimmed_lines

    # Calculate total height
    font = _resolve_font(font_name, current_size)
    line_height = draw.textbbox((0, 0), "Ajgq!#1", font=font)[3] - draw.textbbox((0, 0), "Ajgq!#1", font=font)[1]
    line_spacing = int(line_height * line_spacing_ratio)
    total_height = (line_height * len(best_lines)) + (line_spacing * max(0, len(best_lines) - 1))

    return (best_lines, current_size, total_height)


def calculate_video_placement(
    canvas_width: int,
    canvas_height: int,
    top_used_height: int,
    bottom_margin: int,
    source_width: int,
    source_height: int,
    video_fit: str = "contain",
) -> Dict[str, int]:
    """Calculate contain-fit coordinates and dimensions for source video on canvas. Pure function.

    Preserves source aspect ratio without distortion.
    """
    canvas_w = max(360, int(canvas_width))
    canvas_h = max(640, int(canvas_height))
    src_w = max(2, int(source_width))
    src_h = max(2, int(source_height))

    top_margin = max(0, int(top_used_height))
    bot_margin = max(0, int(bottom_margin))

    available_w = canvas_w
    available_h = max(100, canvas_h - top_margin - bot_margin)

    # Contain mode: scale to fit within available area preserving aspect ratio
    scale = min(available_w / src_w, available_h / src_h)
    target_w = max(2, int(src_w * scale))
    target_h = max(2, int(src_h * scale))

    # libx264 requires even dimensions
    if target_w % 2 != 0:
        target_w -= 1
    if target_h % 2 != 0:
        target_h -= 1

    pos_x = (canvas_w - target_w) // 2
    pos_y = top_margin + (available_h - target_h) // 2

    return {
        "x": max(0, pos_x),
        "y": max(0, pos_y),
        "width": target_w,
        "height": target_h,
        "available_width": available_w,
        "available_height": available_h,
        "top_margin": top_margin,
        "bottom_margin": bot_margin,
    }


def _resolve_asset_path(path: Optional[str]) -> Optional[str]:
    """Resolve an asset path, checking direct path and standard asset folders."""
    if not path:
        return None
    if os.path.isfile(path):
        return path
    for prefix in ("data", "uploads"):
        cand = os.path.join(prefix, path)
        if os.path.isfile(cand):
            return cand
    return None


def generate_header_overlay(
    brand: Union[Brand, Dict[str, Any]],
    template: Union[VisualTemplate, Dict[str, Any]],
    headline: str,
    output_image_path: str,
) -> Dict[str, Any]:
    """Render transparent PNG overlay containing brand header and dynamic headline.

    Uses Pillow with TrueType fonts, circular avatar crop, and auto-downscaling.
    """
    canvas_w = int(_extract_field(template, "width", 1080))
    canvas_h = int(_extract_field(template, "height", 1920))

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    avatar_enabled = bool(_extract_field(template, "avatar_enabled", True))
    avatar_x = int(_extract_field(template, "avatar_x", 60))
    avatar_y = int(_extract_field(template, "avatar_y", 80))
    avatar_size = int(_extract_field(template, "avatar_size", 100))

    avatar_bottom = avatar_y
    if avatar_enabled:
        raw_avatar_path = _extract_field(brand, "avatar_path")
        avatar_path = _resolve_asset_path(raw_avatar_path)
        avatar_placed = False

        if avatar_path and os.path.isfile(avatar_path):
            try:
                with Image.open(avatar_path) as av_img:
                    av_img = av_img.convert("RGBA")
                    av_img = av_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                    # Circular mask
                    mask = Image.new("L", (avatar_size, avatar_size), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)

                    img.paste(av_img, (avatar_x, avatar_y), mask)
                    avatar_placed = True
            except Exception as exc:
                logger.warning("Could not load brand avatar image: %s", exc)

        if not avatar_placed:
            # Draw placeholder circular avatar with brand initial
            brand_name = str(_extract_field(brand, "name", "V"))
            initial = brand_name[:1].upper() if brand_name else "V"
            draw.ellipse(
                [(avatar_x, avatar_y), (avatar_x + avatar_size, avatar_y + avatar_size)],
                fill=(230, 235, 240, 255),
                outline=(200, 205, 210, 255),
                width=2,
            )
            initial_font = _resolve_font(DEFAULT_BRAND_FONT, int(avatar_size * 0.5))
            bbox = draw.textbbox((0, 0), initial, font=initial_font)
            init_w = bbox[2] - bbox[0]
            init_h = bbox[3] - bbox[1]
            draw.text(
                (avatar_x + (avatar_size - init_w) // 2, avatar_y + (avatar_size - init_h) // 2 - 4),
                initial,
                font=initial_font,
                fill=(80, 90, 100, 255),
            )

        avatar_bottom = avatar_y + avatar_size

    # Brand Name and Handle
    brand_name_enabled = bool(_extract_field(template, "brand_name_enabled", True))
    brand_name_font_size = int(_extract_field(template, "brand_name_font_size", 36))
    brand_name_color = _hex_to_rgba(str(_extract_field(template, "brand_name_color", "#111111")))

    handle_font_size = int(_extract_field(template, "handle_font_size", 26))
    handle_color = _hex_to_rgba(str(_extract_field(template, "handle_color", "#666666")))

    header_bottom = avatar_bottom

    if brand_name_enabled:
        text_x = (avatar_x + avatar_size + 24) if avatar_enabled else avatar_x
        name_y = avatar_y + 8 if avatar_enabled else avatar_y
        brand_name = str(_extract_field(brand, "name", "Vale o Clique?"))

        name_font = _resolve_font(DEFAULT_BRAND_FONT, brand_name_font_size)
        draw.text((text_x, name_y), brand_name, font=name_font, fill=brand_name_color)

        handle_text = str(_extract_field(brand, "handle", "@valeoclique"))
        if not handle_text.startswith("@"):
            handle_text = f"@{handle_text}"

        handle_y = name_y + brand_name_font_size + 8
        handle_font = _resolve_font(DEFAULT_HANDLE_FONT, handle_font_size)
        draw.text((text_x, handle_y), handle_text, font=handle_font, fill=handle_color)

        header_bottom = max(avatar_bottom, handle_y + handle_font_size)

    # Dynamic Headline
    headline_enabled = bool(_extract_field(template, "headline_enabled", True))
    headline_font_size = int(_extract_field(template, "headline_font_size", 48))
    headline_color = _hex_to_rgba(str(_extract_field(template, "headline_color", "#111111")))
    headline_max_lines = int(_extract_field(template, "headline_max_lines", 3))
    headline_margin_x = int(_extract_field(template, "headline_margin_x", 60))
    headline_margin_top = int(_extract_field(template, "headline_margin_top", 30))

    final_font_size = headline_font_size
    headline_lines: List[str] = []
    headline_bottom = header_bottom

    if headline_enabled and headline and headline.strip():
        max_headline_w = canvas_w - (2 * headline_margin_x)
        headline_lines, final_font_size, text_h = wrap_and_fit_headline(
            text=headline,
            max_width=max_headline_w,
            max_lines=headline_max_lines,
            base_font_size=headline_font_size,
            font_name=DEFAULT_HEADLINE_FONT,
        )

        hl_font = _resolve_font(DEFAULT_HEADLINE_FONT, final_font_size)
        curr_y = header_bottom + headline_margin_top
        line_height = draw.textbbox((0, 0), "Ajgq!#1", font=hl_font)[3] - draw.textbbox((0, 0), "Ajgq!#1", font=hl_font)[1]
        line_spacing = int(line_height * 0.20)

        for line in headline_lines:
            draw.text((headline_margin_x, curr_y), line, font=hl_font, fill=headline_color)
            curr_y += line_height + line_spacing

        headline_bottom = curr_y

    # Ensure output directory exists and save PNG
    os.makedirs(os.path.dirname(os.path.abspath(output_image_path)) or ".", exist_ok=True)
    img.save(output_image_path, "PNG")

    top_used = headline_bottom + 30
    return {
        "output_path": output_image_path,
        "canvas_width": canvas_w,
        "canvas_height": canvas_h,
        "top_used_height": top_used,
        "headline_lines": headline_lines,
        "final_font_size": final_font_size,
    }


def probe_video_metadata(video_path: str) -> Tuple[int, int, bool]:
    """Probe video for (width, height, has_audio) using ffprobe.

    Falls back to (1080, 1920, True) if ffprobe fails or is unavailable.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            video_path,
        ]
        res = subprocess.check_output(cmd, timeout=15)
        info = json.loads(res.decode("utf-8") or "{}")
        streams = info.get("streams", [])

        width, height = 1080, 1920
        has_audio = False

        for s in streams:
            if s.get("codec_type") == "video":
                width = int(s.get("width", 1080))
                height = int(s.get("height", 1920))
            elif s.get("codec_type") == "audio":
                has_audio = True

        return (width, height, has_audio)
    except Exception as exc:
        logger.warning("ffprobe probe failed on %s: %s (using defaults)", video_path, exc)
        return (1080, 1920, True)


def build_render_ffmpeg_cmd(
    source_path: str,
    overlay_path: str,
    output_path: str,
    canvas_width: int,
    canvas_height: int,
    video_placement: Dict[str, int],
    background_color: str,
    has_audio: bool = True,
    watermark_params: Optional[Dict[str, Any]] = None,
    copy_audio: bool = True,
) -> List[str]:
    """Build the complete FFmpeg command array. Pure function for unit testing.

    Filter graph:
    1. Scales source video to contain-fit dimensions.
    2. Pads to canvas_width x canvas_height with background_color, positioning video at (pos_x, pos_y).
    3. Overlays header and headline PNG at (0, 0).
    4. Overlays optional watermark logo if supplied.
    """
    vw = video_placement["width"]
    vh = video_placement["height"]
    vx = video_placement["x"]
    vy = video_placement["y"]

    bg_color = _hex_to_ffmpeg_color(background_color)

    extra_inputs: List[str] = []
    # Build filter graph
    base_chain = f"[0:v]scale={vw}:{vh},pad={canvas_width}:{canvas_height}:{vx}:{vy}:color={bg_color}[vbase];"
    overlay_chain = "[vbase][1:v]overlay=0:0"

    if watermark_params and watermark_params.get("path"):
        extra_inputs.extend(["-i", watermark_params["path"]])
        logo_chain, lx, ly = logo_filter_chain(
            canvas_width,
            scale=watermark_params.get("scale", 0.18),
            opacity=watermark_params.get("opacity", 0.7),
            margin=watermark_params.get("margin", 0.04),
            position=watermark_params.get("position", DEFAULT_POSITION),
        )
        filter_complex = (
            f"{base_chain}"
            f"{overlay_chain}[vwithheader];"
            f"[2:v]{logo_chain}[wmark];"
            f"[vwithheader][wmark]overlay={lx}:{ly}"
        )
    else:
        filter_complex = f"{base_chain}{overlay_chain}"

    audio_args: List[str] = []
    if has_audio:
        if copy_audio:
            audio_args = ["-c:a", "copy"]
        else:
            audio_args = ["-c:a", "aac", "-b:a", "192k"]
    else:
        audio_args = ["-an"]

    cmd = [
        "ffmpeg",
        "-y",
        "-i", source_path,
        "-i", overlay_path,
        *extra_inputs,
        "-filter_complex", filter_complex,
        *audio_args,
        *x264_video_args(),
        output_path,
    ]
    return cmd


def render_viral_video(
    source_path: str,
    brand: Union[Brand, Dict[str, Any]],
    template: Union[VisualTemplate, Dict[str, Any]],
    headline: str,
    output_path: str,
    watermark: bool = True,
) -> str:
    """Render a 1080x1920 vertical MP4 video with brand header and dynamic headline.

    - Generates Pillow overlay.
    - Preserves source aspect ratio (contain fit).
    - Preserves audio stream (-c:a copy with AAC fallback).
    - Applies watermark if configured.
    - Re-renders fast without touching download or copy modules.
    - Raises ``ComposeError`` on failure.
    """
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Source video file not found: {source_path}")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

    # 1. Probe source dimensions and audio stream
    src_w, src_h, has_audio = probe_video_metadata(source_path)

    # 2. Generate temporary overlay image
    fd, tmp_overlay_path = tempfile.mkstemp(prefix="viral-overlay-", suffix=".png")
    os.close(fd)

    try:
        layout_meta = generate_header_overlay(
            brand=brand,
            template=template,
            headline=headline,
            output_image_path=tmp_overlay_path,
        )

        canvas_w = layout_meta["canvas_width"]
        canvas_h = layout_meta["canvas_height"]
        top_used = layout_meta["top_used_height"]
        bg_color = str(_extract_field(template, "background_color", "#FFFFFF"))
        video_fit = str(_extract_field(template, "video_fit", "contain"))

        # 3. Calculate contain-fit video area
        video_placement = calculate_video_placement(
            canvas_width=canvas_w,
            canvas_height=canvas_h,
            top_used_height=top_used,
            bottom_margin=80,
            source_width=src_w,
            source_height=src_h,
            video_fit=video_fit,
        )

        # 4. Resolve watermark parameters
        watermark_params = None
        watermark_enabled = watermark and bool(_extract_field(template, "watermark_enabled", True))
        raw_logo_path = _extract_field(brand, "logo_path")
        logo_path = _resolve_asset_path(raw_logo_path)
        if watermark_enabled and logo_path and os.path.isfile(logo_path):
            watermark_params = {
                "path": logo_path,
                "opacity": float(_extract_field(template, "watermark_opacity", 0.7)),
                "position": str(_extract_field(template, "watermark_position", "bottom-right")),
                "scale": 0.18,
                "margin": 0.04,
            }

        # 5. Build FFmpeg command (first try with -c:a copy)
        cmd = build_render_ffmpeg_cmd(
            source_path=source_path,
            overlay_path=tmp_overlay_path,
            output_path=output_path,
            canvas_width=canvas_w,
            canvas_height=canvas_h,
            video_placement=video_placement,
            background_color=bg_color,
            has_audio=has_audio,
            watermark_params=watermark_params,
            copy_audio=True,
        )

        timeout = ffmpeg_timeout()
        logger.info("Executing viral studio FFmpeg render → %s", output_path)

        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except subprocess.CalledProcessError as err:
            # If -c:a copy failed, retry once with AAC re-encode
            if has_audio:
                logger.warning(
                    "FFmpeg -c:a copy failed; retrying with AAC audio encode: %s",
                    err.stderr.decode("utf-8", errors="replace")[:300] if err.stderr else "",
                )
                retry_cmd = build_render_ffmpeg_cmd(
                    source_path=source_path,
                    overlay_path=tmp_overlay_path,
                    output_path=output_path,
                    canvas_width=canvas_w,
                    canvas_height=canvas_h,
                    video_placement=video_placement,
                    background_color=bg_color,
                    has_audio=has_audio,
                    watermark_params=watermark_params,
                    copy_audio=False,
                )
                subprocess.run(
                    retry_cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                )
            else:
                raise

        if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            raise ComposeError(f"Render output file was not created or is empty: {output_path}")

        logger.info("✅ Viral video rendered successfully: %s", output_path)
        return output_path

    except subprocess.TimeoutExpired as tex:
        logger.error("❌ FFmpeg render timed out after %ss", timeout)
        raise ComposeError(f"FFmpeg render timed out after {timeout}s") from tex
    except subprocess.CalledProcessError as cpe:
        stderr_msg = cpe.stderr.decode("utf-8", errors="replace") if cpe.stderr else "Unknown error"
        logger.error("❌ FFmpeg render failed: %s", stderr_msg[:500])
        raise ComposeError(f"FFmpeg render failed: {stderr_msg[:300]}") from cpe
    except Exception as exc:
        if isinstance(exc, ComposeError):
            raise
        logger.error("❌ Render viral video failed: %s", exc)
        raise ComposeError(f"Video render failed: {exc}") from exc
    finally:
        with contextlib.suppress(OSError):
            if os.path.exists(tmp_overlay_path):
                os.remove(tmp_overlay_path)


__all__ = [
    "wrap_and_fit_headline",
    "calculate_video_placement",
    "generate_header_overlay",
    "build_render_ffmpeg_cmd",
    "render_viral_video",
]
