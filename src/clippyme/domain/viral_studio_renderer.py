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

from PIL import Image, ImageDraw, ImageFont, ImageOps

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


_HEX_DIGITS = set("0123456789abcdefABCDEF")


def _hex_to_rgba(hex_str: str, alpha: int = 255, default: Tuple[int, int, int] = (0, 0, 0)) -> Tuple[int, int, int, int]:
    """Convert hex color (#RGB, #RGBA, #RRGGBB, #RRGGBBAA) to (r, g, b, alpha) tuple."""
    if isinstance(hex_str, str):
        clean = hex_str.strip().lstrip("#")
        if len(clean) in (3, 4) and all(c in _HEX_DIGITS for c in clean):
            clean = "".join(c * 2 for c in clean)
        if len(clean) in (6, 8) and all(c in _HEX_DIGITS for c in clean):
            try:
                r = int(clean[0:2], 16)
                g = int(clean[2:4], 16)
                b = int(clean[4:6], 16)
                a = int(alpha)
                if len(clean) == 8:
                    a = int(clean[6:8], 16)
                return (r, g, b, a)
            except ValueError:
                pass
    return (*default, int(alpha))


def _hex_to_ffmpeg_color(hex_str: str, default: str = "0xFFFFFF") -> str:
    """Format hex color for FFmpeg filter parameter (e.g. 0xFFFFFF). Validates hex digits."""
    if isinstance(hex_str, str):
        clean = hex_str.strip().lstrip("#")
        if len(clean) in (3, 4) and all(c in _HEX_DIGITS for c in clean):
            clean = "".join(c * 2 for c in clean)
        if len(clean) in (6, 8) and all(c in _HEX_DIGITS for c in clean):
            return f"0x{clean[:6].upper()}"
    return default


def _resolve_font(font_filename: str, size: int) -> ImageFont.ImageFont:
    """Resolve a TrueType font from bundled fonts, system, or fallback to default."""
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

    # Try standard system TrueType fonts (e.g. Linux /usr/share/fonts)
    for sys_font in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "DejaVuSans.ttf",
        "Arial.ttf",
    ):
        try:
            return ImageFont.truetype(sys_font, size)
        except Exception:
            pass

    try:
        return ImageFont.load_default(size=size)
    except Exception:
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
    """Wrap headline text into lines with auto-downscaling to fit max_lines and max_width. Pure function.

    Returns:
        (lines, final_font_size, total_text_height)
    """
    clean_text = " ".join((text or "").strip().split())
    max_w = max(100, int(max_width))
    max_l = max(1, int(max_lines))
    base_size = max(12, int(base_font_size))
    min_size = max(8, min(base_size, int(min_font_size)))

    if not clean_text:
        return ([], base_size, 0)

    words = clean_text.split()
    dummy_img = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy_img)

    current_size = base_size
    best_lines: List[str] = []
    line_spacing_ratio = 0.20

    while current_size >= min_size:
        font = _resolve_font(font_name, current_size)
        lines: List[str] = []
        current_line: List[str] = []
        has_overflow_word = False

        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_w = bbox[2] - bbox[0]

            if line_w <= max_w:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                    word_bbox = draw.textbbox((0, 0), word, font=font)
                    if (word_bbox[2] - word_bbox[0]) > max_w:
                        has_overflow_word = True
                else:
                    # Single word is wider than max_w
                    lines.append(word)
                    has_overflow_word = True
                    current_line = []

        if current_line:
            lines.append(" ".join(current_line))

        best_lines = lines
        if len(lines) <= max_l and not has_overflow_word:
            break
        else:
            current_size -= 2

    current_size = max(min_size, current_size)
    font = _resolve_font(font_name, current_size)

    # If still exceeding max_l at min_size, truncate lines
    if len(best_lines) > max_l:
        trimmed_lines = best_lines[: max_l - 1]
        overflow_words = " ".join(best_lines[max_l - 1 :])
        truncated = overflow_words
        while truncated and (draw.textbbox((0, 0), f"{truncated}...", font=font)[2] - draw.textbbox((0, 0), f"{truncated}...", font=font)[0]) > max_w:
            parts = truncated.split()
            if len(parts) > 1:
                truncated = " ".join(parts[:-1])
            else:
                truncated = truncated[:-1].rstrip("\u200d\ufe0f ")
        trimmed_lines.append(f"{truncated}..." if truncated else "...")
        best_lines = trimmed_lines

    # Ensure every single line is bounded within max_w
    bounded_lines: List[str] = []
    for line in best_lines:
        line_w = draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0]
        if line_w > max_w:
            t = line
            while t and (draw.textbbox((0, 0), f"{t}...", font=font)[2] - draw.textbbox((0, 0), f"{t}...", font=font)[0]) > max_w:
                t = t[:-1].rstrip("\u200d\ufe0f ")
            bounded_lines.append(f"{t}..." if t else "...")
        else:
            bounded_lines.append(line)
    best_lines = bounded_lines

    # Calculate total height
    bbox_h = draw.textbbox((0, 0), "Ajgq!#1", font=font)
    line_height = max(10, bbox_h[3] - bbox_h[1])
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
    Guarantees even coordinates (x, y, width, height) for YUV420p / libx264 alignment.
    """
    canvas_w = max(360, int(canvas_width))
    if canvas_w % 2 != 0:
        canvas_w -= 1
    canvas_h = max(640, int(canvas_height))
    if canvas_h % 2 != 0:
        canvas_h -= 1

    src_w = max(2, int(source_width))
    src_h = max(2, int(source_height))

    top_margin = max(0, int(top_used_height))
    bot_margin = max(0, int(bottom_margin))

    available_w = canvas_w
    available_h = max(100, canvas_h - top_margin - bot_margin)
    if available_h % 2 != 0:
        available_h -= 1

    # Contain mode: scale to fit within available area preserving aspect ratio
    scale = min(available_w / src_w, available_h / src_h)
    target_w = max(2, int(src_w * scale))
    target_h = max(2, int(src_h * scale))

    # libx264 / YUV420p requires even dimensions and offsets
    if target_w % 2 != 0:
        target_w -= 1
    if target_h % 2 != 0:
        target_h -= 1
    target_w = max(2, target_w)
    target_h = max(2, target_h)

    pos_x = (canvas_w - target_w) // 2
    pos_y = top_margin + (available_h - target_h) // 2

    if pos_x % 2 != 0:
        pos_x -= 1
    if pos_y % 2 != 0:
        pos_y -= 1

    pos_x = max(0, pos_x)
    pos_y = max(0, pos_y)

    if pos_y + target_h > canvas_h:
        pos_y = canvas_h - target_h
        if pos_y % 2 != 0:
            pos_y -= 1
        pos_y = max(0, pos_y)

    return {
        "x": pos_x,
        "y": pos_y,
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
    clean = path.lstrip("/")
    for prefix in ("data", "uploads", ""):
        cand = os.path.join(prefix, clean) if prefix else clean
        if os.path.isfile(cand):
            return cand
        cand_root = os.path.join(_REPO_ROOT, cand)
        if os.path.isfile(cand_root):
            return cand_root
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
    if canvas_w % 2 != 0:
        canvas_w -= 1
    canvas_h = int(_extract_field(template, "height", 1920))
    if canvas_h % 2 != 0:
        canvas_h -= 1

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    avatar_enabled = bool(_extract_field(template, "avatar_enabled", True))
    avatar_x = max(0, int(_extract_field(template, "avatar_x", 60)))
    avatar_y = max(0, int(_extract_field(template, "avatar_y", 80)))
    avatar_size = max(20, int(_extract_field(template, "avatar_size", 100)))

    avatar_bottom = 0
    if avatar_enabled:
        raw_avatar_path = _extract_field(brand, "avatar_path") or _extract_field(brand, "avatar_url")
        avatar_path = _resolve_asset_path(raw_avatar_path)
        avatar_placed = False

        if avatar_path and os.path.isfile(avatar_path):
            try:
                with Image.open(avatar_path) as av_img:
                    av_img = av_img.convert("RGBA")
                    av_img = ImageOps.fit(av_img, (avatar_size, avatar_size), Image.Resampling.LANCZOS)
                    # Circular mask (0-indexed boundary avatar_size - 1)
                    mask = Image.new("L", (avatar_size, avatar_size), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, avatar_size - 1, avatar_size - 1), fill=255)

                    img.paste(av_img, (avatar_x, avatar_y), mask)
                    avatar_placed = True
            except Exception as exc:
                logger.warning("Could not load brand avatar image: %s", exc)

        if not avatar_placed:
            # Draw placeholder circular avatar with brand initial (pick first alphanumeric char)
            brand_name = str(_extract_field(brand, "name", "V")).strip()
            alnum_chars = re.sub(r"[^\w]", "", brand_name or "")
            initial = alnum_chars[:1].upper() if alnum_chars else (brand_name[:1].upper() if brand_name else "V")
            if not initial:
                initial = "V"
            draw.ellipse(
                [(avatar_x, avatar_y), (avatar_x + avatar_size - 1, avatar_y + avatar_size - 1)],
                fill=(230, 235, 240, 255),
                outline=(200, 205, 210, 255),
                width=2,
            )
            initial_font = _resolve_font(DEFAULT_BRAND_FONT, max(10, int(avatar_size * 0.5)))
            bbox = draw.textbbox((0, 0), initial, font=initial_font)
            init_w = bbox[2] - bbox[0]
            init_h = bbox[3] - bbox[1]
            draw.text(
                (avatar_x + (avatar_size - init_w) // 2 - bbox[0], avatar_y + (avatar_size - init_h) // 2 - bbox[1]),
                initial,
                font=initial_font,
                fill=(80, 90, 100, 255),
            )

        avatar_bottom = avatar_y + avatar_size

    # Brand Name and Handle
    brand_name_enabled = bool(_extract_field(template, "brand_name_enabled", True))
    brand_name_font_size = max(8, int(_extract_field(template, "brand_name_font_size", 36)))
    brand_name_color = _hex_to_rgba(str(_extract_field(template, "brand_name_color", "#111111")))

    handle_font_size = max(8, int(_extract_field(template, "handle_font_size", 26)))
    handle_color = _hex_to_rgba(str(_extract_field(template, "handle_color", "#666666")))

    header_bottom = avatar_bottom

    if brand_name_enabled:
        text_x = (avatar_x + avatar_size + 24) if avatar_enabled else avatar_x
        name_y = avatar_y + 8 if avatar_enabled else 80
        brand_name = str(_extract_field(brand, "name", "Vale o Clique?")).strip()

        max_text_w = max(100, canvas_w - text_x - 60)
        name_font = _resolve_font(DEFAULT_BRAND_FONT, brand_name_font_size)

        if brand_name:
            # Truncate brand name if wider than available canvas space
            display_name = brand_name
            if (draw.textbbox((0, 0), display_name, font=name_font)[2] - draw.textbbox((0, 0), display_name, font=name_font)[0]) > max_text_w:
                while display_name and (draw.textbbox((0, 0), f"{display_name}...", font=name_font)[2] - draw.textbbox((0, 0), f"{display_name}...", font=name_font)[0]) > max_text_w:
                    display_name = display_name[:-1].rstrip()
                display_name = f"{display_name}..." if display_name else "..."

            draw.text((text_x, name_y), display_name, font=name_font, fill=brand_name_color)
            header_bottom = max(avatar_bottom, name_y + brand_name_font_size)

        raw_handle = _extract_field(brand, "handle")
        clean_handle = str(raw_handle).strip().lstrip("@") if raw_handle is not None else ""
        if clean_handle:
            display_handle = f"@{clean_handle}"
            handle_y = (name_y + brand_name_font_size + 8) if brand_name else name_y
            handle_font = _resolve_font(DEFAULT_HANDLE_FONT, handle_font_size)

            # Truncate handle if wider than available canvas space
            if (draw.textbbox((0, 0), display_handle, font=handle_font)[2] - draw.textbbox((0, 0), display_handle, font=handle_font)[0]) > max_text_w:
                while clean_handle and (draw.textbbox((0, 0), f"@{clean_handle}...", font=handle_font)[2] - draw.textbbox((0, 0), f"@{clean_handle}...", font=handle_font)[0]) > max_text_w:
                    clean_handle = clean_handle[:-1].rstrip()
                display_handle = f"@{clean_handle}..." if clean_handle else "..."

            draw.text((text_x, handle_y), display_handle, font=handle_font, fill=handle_color)
            header_bottom = max(header_bottom, handle_y + handle_font_size)

    # Dynamic Headline
    headline_enabled = bool(_extract_field(template, "headline_enabled", True))
    headline_font_size = max(12, int(_extract_field(template, "headline_font_size", 48)))
    headline_color = _hex_to_rgba(str(_extract_field(template, "headline_color", "#111111")))
    headline_max_lines = max(1, int(_extract_field(template, "headline_max_lines", 3)))
    headline_margin_x = max(0, int(_extract_field(template, "headline_margin_x", 60)))
    headline_margin_top = max(0, int(_extract_field(template, "headline_margin_top", 30)))

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
        curr_y = (header_bottom + headline_margin_top) if header_bottom > 0 else 80
        line_height = draw.textbbox((0, 0), "Ajgq!#1", font=hl_font)[3] - draw.textbbox((0, 0), "Ajgq!#1", font=hl_font)[1]
        line_spacing = int(line_height * 0.20)

        for line in headline_lines:
            draw.text((headline_margin_x, curr_y), line, font=hl_font, fill=headline_color)
            curr_y += line_height + line_spacing

        headline_bottom = curr_y

    # Ensure output directory exists and save PNG
    os.makedirs(os.path.dirname(os.path.abspath(output_image_path)) or ".", exist_ok=True)
    img.save(output_image_path, "PNG")

    top_used = (headline_bottom + 30) if headline_bottom > 0 else 0
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
        primary_video: Optional[Dict[str, Any]] = None

        for s in streams:
            if s.get("codec_type") == "video":
                disposition = s.get("disposition") or {}
                if not disposition.get("attached_pic"):
                    primary_video = s
                    break
                elif primary_video is None:
                    primary_video = s

        if primary_video:
            width = max(2, int(primary_video.get("width") or 1080))
            height = max(2, int(primary_video.get("height") or 1920))
            # Detect rotation metadata (e.g. mobile camera 90/270)
            rotate = (primary_video.get("tags") or {}).get("rotate")
            if not rotate:
                for sd in primary_video.get("side_data_list") or []:
                    if isinstance(sd, dict) and "rotation" in sd:
                        rotate = sd["rotation"]
                        break
            if rotate:
                try:
                    if abs(int(float(rotate))) in (90, 270):
                        width, height = height, width
                except (ValueError, TypeError):
                    pass

        for s in streams:
            if s.get("codec_type") == "audio":
                has_audio = True
                break

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
    2. Overlays optional watermark logo onto the video footage (Sobre o vídeo).
    3. Pads to canvas_width x canvas_height with background_color, positioning video at (pos_x, pos_y).
    4. Overlays transparent header and headline PNG at (0, 0).
    """
    vw = video_placement["width"]
    vh = video_placement["height"]
    vx = video_placement["x"]
    vy = video_placement["y"]

    cw = canvas_width - (canvas_width % 2)
    ch = canvas_height - (canvas_height % 2)

    bg_color = _hex_to_ffmpeg_color(background_color)

    extra_inputs: List[str] = []
    # Build filter graph
    if watermark_params and watermark_params.get("path"):
        extra_inputs.extend(["-i", watermark_params["path"]])
        logo_chain, lx, ly = logo_filter_chain(
            vw,
            scale=watermark_params.get("scale", 0.18),
            opacity=watermark_params.get("opacity", 0.7),
            margin=watermark_params.get("margin", 0.04),
            position=watermark_params.get("position", DEFAULT_POSITION),
        )
        filter_complex = (
            f"[0:v]scale={vw}:{vh}[vscaled];"
            f"[2:v]{logo_chain}[wmark];"
            f"[vscaled][wmark]overlay={lx}:{ly}[vwithlogo];"
            f"[vwithlogo]pad={cw}:{ch}:{vx}:{vy}:color={bg_color}[vbase];"
            f"[vbase][1:v]overlay=0:0"
        )
    else:
        filter_complex = (
            f"[0:v]scale={vw}:{vh},pad={cw}:{ch}:{vx}:{vy}:color={bg_color}[vbase];"
            f"[vbase][1:v]overlay=0:0"
        )

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
        configured_bottom_margin = _extract_field(template, "bottom_margin")
        if configured_bottom_margin is not None:
            effective_bottom_margin = int(configured_bottom_margin)
        else:
            effective_bottom_margin = 80 if top_used > 0 else 0

        video_placement = calculate_video_placement(
            canvas_width=canvas_w,
            canvas_height=canvas_h,
            top_used_height=top_used,
            bottom_margin=effective_bottom_margin,
            source_width=src_w,
            source_height=src_h,
            video_fit=video_fit,
        )

        # 4. Resolve watermark parameters
        watermark_params = None
        watermark_enabled = watermark and bool(_extract_field(template, "watermark_enabled", True))
        raw_logo_path = _extract_field(brand, "logo_path") or _extract_field(brand, "logo_url")
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
        with contextlib.suppress(OSError):
            if os.path.exists(output_path):
                os.remove(output_path)
        logger.error("❌ FFmpeg render timed out after %ss", timeout)
        raise ComposeError(f"FFmpeg render timed out after {timeout}s") from tex
    except subprocess.CalledProcessError as cpe:
        with contextlib.suppress(OSError):
            if os.path.exists(output_path):
                os.remove(output_path)
        stderr_msg = cpe.stderr.decode("utf-8", errors="replace") if cpe.stderr else "Unknown error"
        logger.error("❌ FFmpeg render failed: %s", stderr_msg[:500])
        raise ComposeError(f"FFmpeg render failed: {stderr_msg[:300]}") from cpe
    except Exception as exc:
        with contextlib.suppress(OSError):
            if os.path.exists(output_path):
                os.remove(output_path)
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
