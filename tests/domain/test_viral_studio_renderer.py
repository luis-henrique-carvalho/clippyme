"""Unit and integration tests for viral_studio_renderer (Milestone 4)."""
import os
import subprocess
from unittest.mock import patch

import pytest
from PIL import Image

from clippyme.api.viral_studio_schemas import Brand, VisualTemplate
from clippyme.domain import viral_studio_renderer
from clippyme.domain.errors import ComposeError


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except Exception:
        return False


@pytest.fixture
def test_brand(tmp_path):
    # Create dummy avatar and logo images
    avatar_path = str(tmp_path / "avatar.png")
    Image.new("RGBA", (120, 120), (255, 0, 0, 255)).save(avatar_path)

    logo_path = str(tmp_path / "logo.png")
    Image.new("RGBA", (80, 80), (0, 255, 0, 200)).save(logo_path)

    return Brand.model_construct(
        id="vale-o-clique",
        name="Vale o Clique?",
        handle="@valeoclique",
        avatar_path=avatar_path,
        logo_path=logo_path,
        default_cta="Confira os achadinhos no link da bio!",
    )


@pytest.fixture
def test_template():
    return VisualTemplate(
        id="classic-affiliate",
        width=1080,
        height=1920,
        background_color="#FFFFFF",
        avatar_enabled=True,
        brand_name_enabled=True,
        headline_enabled=True,
        watermark_enabled=True,
        video_fit="contain",
        headline_font_size=48,
        headline_max_lines=3,
        headline_margin_x=60,
    )


# ============================================================================
# Layout Calculation Tests (Pure Math)
# ============================================================================

def test_calculate_video_placement_contain_landscape_16_9():
    """16:9 video (1920x1080) placed on 1080x1920 canvas."""
    placement = viral_studio_renderer.calculate_video_placement(
        canvas_width=1080,
        canvas_height=1920,
        top_used_height=320,
        bottom_margin=80,
        source_width=1920,
        source_height=1080,
    )
    assert placement["width"] == 1080
    # Expected height: 1080 * (1080 / 1920) = 607.5 -> 606 or 608 even
    assert placement["height"] % 2 == 0
    assert abs(placement["height"] - 608) <= 2
    assert placement["x"] == 0
    assert placement["y"] >= 320
    assert placement["width"] <= 1080
    assert placement["y"] + placement["height"] <= 1920 - 80


def test_calculate_video_placement_contain_vertical_9_16():
    """9:16 video (1080x1920) placed on 1080x1920 canvas with top clearance."""
    placement = viral_studio_renderer.calculate_video_placement(
        canvas_width=1080,
        canvas_height=1920,
        top_used_height=350,
        bottom_margin=80,
        source_width=1080,
        source_height=1920,
    )
    available_h = 1920 - 350 - 80  # 1490
    assert placement["height"] <= available_h
    assert placement["height"] % 2 == 0
    assert placement["width"] % 2 == 0
    # Scaled preserving 9:16 aspect
    expected_w = int(available_h * (1080 / 1920))
    assert abs(placement["width"] - expected_w) <= 2
    assert placement["x"] >= 0
    assert placement["y"] >= 350


def test_calculate_video_placement_contain_square_1_1():
    """1:1 video (1080x1080) placed on 1080x1920 canvas."""
    placement = viral_studio_renderer.calculate_video_placement(
        canvas_width=1080,
        canvas_height=1920,
        top_used_height=300,
        bottom_margin=80,
        source_width=1080,
        source_height=1080,
    )
    assert placement["width"] == placement["height"]
    assert placement["width"] <= 1080
    assert placement["width"] % 2 == 0
    assert placement["x"] == 0
    assert placement["y"] >= 300


# ============================================================================
# Dynamic Headline Wrapping & Auto-Downscaling Tests
# ============================================================================

def test_wrap_and_fit_headline_short_text():
    headline = "Olha que achadinho incrível!"
    lines, font_size, height = viral_studio_renderer.wrap_and_fit_headline(
        text=headline,
        max_width=960,
        max_lines=3,
        base_font_size=48,
    )
    assert len(lines) <= 2
    assert font_size == 48
    assert height > 0
    assert "achadinho" in " ".join(lines)


def test_wrap_and_fit_headline_auto_downscales_long_text():
    long_headline = (
        "Esse organizador giratório incrível de armários de cozinha vai mudar a sua vida "
        "e deixar tudo no lugar certo sem perder tempo!"
    )
    lines, font_size, height = viral_studio_renderer.wrap_and_fit_headline(
        text=long_headline,
        max_width=960,
        max_lines=3,
        base_font_size=48,
        min_font_size=24,
    )
    assert len(lines) <= 3
    # Downscaled to fit inside 3 lines
    assert font_size < 48
    assert height > 0


def test_wrap_and_fit_headline_supports_accents_and_emojis():
    headline = "Quem tem cozinha pequena precisa ver isso! 😱 Diga adeus à bagunça ✨"
    lines, font_size, height = viral_studio_renderer.wrap_and_fit_headline(
        text=headline,
        max_width=960,
        max_lines=3,
        base_font_size=48,
    )
    assert len(lines) <= 3
    full_text = " ".join(lines)
    assert "😱" in full_text
    assert "bagunça" in full_text
    assert "pequena" in full_text


# ============================================================================
# Pillow Overlay Generation Tests
# ============================================================================

def test_generate_header_overlay_produces_valid_transparent_png(tmp_path, test_brand, test_template):
    overlay_out = str(tmp_path / "header_overlay.png")
    headline = "Quem tem armário pequeno precisa ver isso! 😱"

    meta = viral_studio_renderer.generate_header_overlay(
        brand=test_brand,
        template=test_template,
        headline=headline,
        output_image_path=overlay_out,
    )
    assert os.path.isfile(overlay_out)
    assert meta["canvas_width"] == 1080
    assert meta["canvas_height"] == 1920
    assert meta["top_used_height"] > 200
    assert len(meta["headline_lines"]) >= 1

    # Verify Pillow can open and check transparency
    with Image.open(overlay_out) as img:
        assert img.size == (1080, 1920)
        assert img.mode == "RGBA"
        # Check bottom area is transparent
        bottom_pixel = img.getpixel((540, 1500))
        assert bottom_pixel[3] == 0  # Fully transparent alpha


def test_generate_header_overlay_handles_missing_avatar_file(tmp_path, test_template):
    brand_no_avatar = Brand(
        id="no-avatar-brand",
        name="Loja das Ofertas",
        handle="@lojaofertas",
        avatar_path=None,
    )
    overlay_out = str(tmp_path / "no_avatar_overlay.png")
    meta = viral_studio_renderer.generate_header_overlay(
        brand=brand_no_avatar,
        template=test_template,
        headline="Novidade na área!",
        output_image_path=overlay_out,
    )
    assert os.path.isfile(overlay_out)
    assert meta["top_used_height"] > 150


# ============================================================================
# FFmpeg Command Construction Tests (Pure Function)
# ============================================================================

def test_build_render_ffmpeg_cmd_standard_structure():
    placement = {
        "x": 0,
        "y": 420,
        "width": 1080,
        "height": 1080,
    }
    cmd = viral_studio_renderer.build_render_ffmpeg_cmd(
        source_path="/tmp/source.mp4",
        overlay_path="/tmp/overlay.png",
        output_path="/tmp/rendered.mp4",
        canvas_width=1080,
        canvas_height=1920,
        video_placement=placement,
        background_color="#FFFFFF",
        has_audio=True,
        copy_audio=True,
    )
    assert cmd[0] == "ffmpeg"
    assert "-i" in cmd
    assert "/tmp/source.mp4" in cmd
    assert "/tmp/overlay.png" in cmd
    assert "-filter_complex" in cmd
    idx = cmd.index("-filter_complex")
    filter_graph = cmd[idx + 1]

    # Filter graph containment
    assert "scale=1080:1080" in filter_graph
    assert "pad=1080:1920:0:420:color=0xFFFFFF" in filter_graph
    assert "overlay=0:0" in filter_graph

    # Audio copy stream
    assert "-c:a" in cmd
    audio_idx = cmd.index("-c:a")
    assert cmd[audio_idx + 1] == "copy"

    # libx264 settings
    assert "-c:v" in cmd
    assert "libx264" in cmd
    assert "/tmp/rendered.mp4" == cmd[-1]


def test_build_render_ffmpeg_cmd_with_watermark():
    placement = {"x": 0, "y": 400, "width": 1080, "height": 608}
    watermark_params = {
        "path": "/tmp/logo.png",
        "opacity": 0.8,
        "position": "bottom-right",
        "scale": 0.18,
        "margin": 0.04,
    }
    cmd = viral_studio_renderer.build_render_ffmpeg_cmd(
        source_path="/tmp/src.mp4",
        overlay_path="/tmp/ov.png",
        output_path="/tmp/out.mp4",
        canvas_width=1080,
        canvas_height=1920,
        video_placement=placement,
        background_color="#1A1A1A",
        has_audio=False,
        watermark_params=watermark_params,
    )
    assert "/tmp/logo.png" in cmd
    assert "-an" in cmd  # No audio flag

    idx = cmd.index("-filter_complex")
    filter_graph = cmd[idx + 1]
    assert "color=0x1A1A1A" in filter_graph
    assert "[2:v]" in filter_graph
    assert "colorchannelmixer=aa=0.800" in filter_graph


def test_build_render_ffmpeg_cmd_aac_fallback_audio():
    placement = {"x": 0, "y": 400, "width": 1080, "height": 608}
    cmd = viral_studio_renderer.build_render_ffmpeg_cmd(
        source_path="/tmp/src.mp4",
        overlay_path="/tmp/ov.png",
        output_path="/tmp/out.mp4",
        canvas_width=1080,
        canvas_height=1920,
        video_placement=placement,
        background_color="#FFFFFF",
        has_audio=True,
        copy_audio=False,  # Fallback AAC re-encode
    )
    assert "-c:a" in cmd
    audio_idx = cmd.index("-c:a")
    assert cmd[audio_idx + 1] == "aac"


# ============================================================================
# Error Handling & Edge Cases
# ============================================================================

def test_render_viral_video_missing_source_file_raises(test_brand, test_template):
    with pytest.raises(FileNotFoundError):
        viral_studio_renderer.render_viral_video(
            source_path="/tmp/nonexistent_source_video_123.mp4",
            brand=test_brand,
            template=test_template,
            headline="Test",
            output_path="/tmp/out.mp4",
        )


def test_render_viral_video_ffmpeg_timeout_raises_compose_error(tmp_path, test_brand, test_template):
    src = tmp_path / "dummy_source.mp4"
    src.write_bytes(b"\x00" * 100)
    out = tmp_path / "out.mp4"

    with patch("clippyme.domain.viral_studio_renderer.probe_video_metadata", return_value=(1080, 1920, True)), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10)):
        with pytest.raises(ComposeError) as exc:
            viral_studio_renderer.render_viral_video(
                source_path=str(src),
                brand=test_brand,
                template=test_template,
                headline="Headline Test",
                output_path=str(out),
            )
        assert "timed out" in str(exc.value).lower()


def test_render_viral_video_retry_aac_on_copy_error(tmp_path, test_brand, test_template):
    """When -c:a copy fails, render_viral_video automatically retries with AAC."""
    src = tmp_path / "dummy_source.mp4"
    src.write_bytes(b"\x00" * 100)
    out = tmp_path / "out.mp4"

    calls = []

    def mock_subprocess_run(cmd, **kwargs):
        calls.append(cmd)
        if len(calls) == 1:
            # First attempt with -c:a copy fails
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr=b"Could not copy audio stream")
        # Second attempt with AAC succeeds
        out.write_bytes(b"\x00" * 200)
        return subprocess.CompletedProcess(cmd, 0)

    with patch("clippyme.domain.viral_studio_renderer.probe_video_metadata", return_value=(1080, 1920, True)), \
         patch("subprocess.run", side_effect=mock_subprocess_run):
        res = viral_studio_renderer.render_viral_video(
            source_path=str(src),
            brand=test_brand,
            template=test_template,
            headline="Headline Test",
            output_path=str(out),
        )
        assert res == str(out)
        assert len(calls) == 2
        # First call has copy
        assert "copy" in calls[0]
        # Second call has aac
        assert "aac" in calls[1]


# ============================================================================
# Synthetic Video Real FFmpeg Integration Smoke Test
# ============================================================================

def test_synthetic_video_render_smoke_test(tmp_path, test_brand, test_template):
    """Real FFmpeg execution creating a synthetic source video and rendering 1080x1920 MP4."""
    if not _has_ffmpeg():
        pytest.skip("FFmpeg not installed on host machine (runs in Docker integration suite)")

    src = str(tmp_path / "synthetic_source.mp4")
    # Generate 1-second synthetic 640x360 video with sine audio
    gen_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=640x360:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        src,
    ]
    subprocess.run(gen_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert os.path.isfile(src) and os.path.getsize(src) > 0

    rendered = str(tmp_path / "viral_rendered.mp4")
    headline = "Olha esse achadinho genial para a cozinha! 😱"

    output = viral_studio_renderer.render_viral_video(
        source_path=src,
        brand=test_brand,
        template=test_template,
        headline=headline,
        output_path=rendered,
        watermark=True,
    )
    assert output == rendered
    assert os.path.isfile(rendered)
    assert os.path.getsize(rendered) > 0

    # Probe rendered output with ffprobe
    probe_cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        rendered,
    ]
    probe_res = subprocess.check_output(probe_cmd)
    import json
    info = json.loads(probe_res.decode("utf-8"))
    streams = info.get("streams", [])

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    assert len(video_streams) == 1
    assert video_streams[0]["width"] == 1080
    assert video_streams[0]["height"] == 1920
    assert len(audio_streams) == 1


# ============================================================================
# Additional Edge Cases
# ============================================================================

def test_wrap_and_fit_headline_empty_or_whitespace():
    lines, font_size, height = viral_studio_renderer.wrap_and_fit_headline("", 960, 3)
    assert lines == []
    assert height == 0

    lines, font_size, height = viral_studio_renderer.wrap_and_fit_headline("    ", 960, 3)
    assert lines == []
    assert height == 0


def test_calculate_video_placement_extreme_dimensions():
    # 8K video
    p_8k = viral_studio_renderer.calculate_video_placement(1080, 1920, 200, 50, 7680, 4320)
    assert p_8k["width"] == 1080
    assert p_8k["height"] % 2 == 0
    assert p_8k["width"] % 2 == 0
    assert p_8k["y"] >= 200

    # Tiny 20x20 video
    p_tiny = viral_studio_renderer.calculate_video_placement(1080, 1920, 200, 50, 20, 20)
    assert p_tiny["width"] == 1080
    assert p_tiny["height"] == 1080


def test_generate_header_overlay_disabled_components(tmp_path, test_brand):
    tmpl = VisualTemplate(
        id="barebones",
        avatar_enabled=False,
        brand_name_enabled=False,
        headline_enabled=False,
    )
    out_png = str(tmp_path / "barebones.png")
    meta = viral_studio_renderer.generate_header_overlay(
        brand=test_brand,
        template=tmpl,
        headline="Should not appear",
        output_image_path=out_png,
    )
    assert os.path.isfile(out_png)
    assert meta["headline_lines"] == []

