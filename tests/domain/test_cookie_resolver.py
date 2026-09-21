"""Unit tests for multi-platform cookie resolver."""
from __future__ import annotations

import os
from enum import Enum
import pytest

from clippyme.domain import cookie_resolver as resolver


class MockPlatform(Enum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    OTHER = "other"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("youtube", "youtube"),
        ("YOUTUBE", "youtube"),
        ("instagram", "instagram"),
        ("tiktok", "tiktok"),
        ("https://www.youtube.com/shorts/0vO_Fo6-lCQ", "youtube"),
        ("https://youtu.be/0vO_Fo6-lCQ", "youtube"),
        ("https://www.instagram.com/reel/C12345/", "instagram"),
        ("https://instagr.am/p/C12345/", "instagram"),
        ("https://www.tiktok.com/@user/video/789101112", "tiktok"),
        ("https://vm.tiktok.com/ZM8abc/", "tiktok"),
        (MockPlatform.YOUTUBE, "youtube"),
        (MockPlatform.INSTAGRAM, "instagram"),
        (MockPlatform.TIKTOK, "tiktok"),
        (MockPlatform.OTHER, None),
        ("https://vimeo.com/12345", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_platform_name(raw, expected):
    assert resolver.normalize_platform_name(raw) == expected


def test_get_platform_cookie_path():
    path = resolver.get_platform_cookie_path("youtube")
    assert path.replace("\\", "/").endswith("data/cookies/youtube.txt")

    path_url = resolver.get_platform_cookie_path("https://www.instagram.com/reel/123")
    assert path_url.replace("\\", "/").endswith("data/cookies/instagram.txt")


def test_resolve_platform_cookies_specific_priority(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cookies_dir = tmp_path / "data" / "cookies"
    cookies_dir.mkdir(parents=True, exist_ok=True)

    yt_cookie = cookies_dir / "youtube.txt"
    yt_cookie.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tSID\t123\n")

    legacy_cookie = tmp_path / "data" / "cookies.txt"
    legacy_cookie.write_text("# Netscape HTTP Cookie File\n.legacy.com\tTRUE\t/\tFALSE\t0\tSID\t999\n")

    # For YouTube target, should pick youtube.txt
    resolved_yt = resolver.resolve_platform_cookies("https://www.youtube.com/shorts/123")
    assert resolved_yt is not None
    assert os.path.samefile(resolved_yt, yt_cookie)

    # For Instagram target (no specific file), should fallback to legacy cookies.txt
    resolved_ig = resolver.resolve_platform_cookies("https://www.instagram.com/reel/123")
    assert resolved_ig is not None
    assert os.path.samefile(resolved_ig, legacy_cookie)


def test_resolve_platform_cookies_fallback_to_legacy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    legacy_cookie = data_dir / "cookies.txt"
    legacy_cookie.write_text("# Netscape HTTP Cookie File\n")

    resolved = resolver.resolve_platform_cookies("youtube")
    assert resolved is not None
    assert os.path.samefile(resolved, legacy_cookie)


def test_resolve_platform_cookies_none_when_empty_or_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    cookies_dir = data_dir / "cookies"
    cookies_dir.mkdir(parents=True, exist_ok=True)

    # Empty files should be ignored
    (cookies_dir / "youtube.txt").touch()
    (data_dir / "cookies.txt").touch()

    assert resolver.resolve_platform_cookies("youtube") is None
    assert resolver.resolve_platform_cookies("instagram") is None
    assert resolver.resolve_platform_cookies(None) is None


def test_get_all_cookies_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cookies_dir = tmp_path / "data" / "cookies"
    cookies_dir.mkdir(parents=True, exist_ok=True)

    # Initial status - nothing configured
    status = resolver.get_all_cookies_status()
    assert status == {
        "youtube": False,
        "instagram": False,
        "tiktok": False,
        "legacy": False,
        "configured": False,
    }

    # Add tiktok cookies
    (cookies_dir / "tiktok.txt").write_text("# Netscape Cookie")
    status = resolver.get_all_cookies_status()
    assert status["tiktok"] is True
    assert status["youtube"] is False
    assert status["configured"] is True

    # Add legacy cookies
    (tmp_path / "data" / "cookies.txt").write_text("# Legacy Cookie")
    status = resolver.get_all_cookies_status()
    assert status["legacy"] is True
    assert status["configured"] is True
