"""Centralized, multi-platform cookie resolution for ClippyMe.

Provides isolated cookie file paths per platform (YouTube, Instagram, TikTok)
stored in ``data/cookies/{platform}.txt`` with automatic fallback to the legacy
``data/cookies.txt`` file. Pure domain logic (host-testable without FastAPI/cv2).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse

COOKIES_DIR = os.path.join("data", "cookies")
LEGACY_COOKIES_PATH = os.path.join("data", "cookies.txt")

SUPPORTED_COOKIE_PLATFORMS = ("youtube", "instagram", "tiktok")


def normalize_platform_name(target: Any) -> Optional[str]:
    """Normalize a platform name, hostname, or URL into a canonical platform key."""
    if target is None:
        return None
    if hasattr(target, "value"):
        target = target.value
    if not isinstance(target, str):
        target = str(target)


    raw = target.strip().lower()
    if raw in SUPPORTED_COOKIE_PLATFORMS:
        return raw

    # Handle PlatformType enum values or string representations
    if "youtube" in raw or "youtu.be" in raw:
        return "youtube"
    if "instagram" in raw or "instagr.am" in raw:
        return "instagram"
    if "tiktok" in raw:
        return "tiktok"

    # If it's a URL, parse hostname
    try:
        if "://" in raw or raw.startswith("//"):
            parsed = urlparse(raw)
            host = (parsed.hostname or "").lower()
            if "youtube.com" in host or "youtu.be" in host:
                return "youtube"
            if "instagram.com" in host or "instagr.am" in host:
                return "instagram"
            if "tiktok.com" in host:
                return "tiktok"
    except Exception:
        pass

    return None


def get_platform_cookie_path(platform: str) -> str:
    """Return the canonical storage path for a platform's cookie file."""
    norm = normalize_platform_name(platform) or platform.lower().strip()
    return os.path.join(COOKIES_DIR, f"{norm}.txt")


def resolve_platform_cookies(target: str | None = None) -> Optional[str]:
    """Resolve the absolute path to an existing, non-empty cookies file.

    Checks:
    1. Dedicated platform file: ``data/cookies/{platform}.txt``
    2. Legacy unified file fallback: ``data/cookies.txt``

    Returns None if no non-empty cookies file exists.
    """
    platform = normalize_platform_name(target)
    if platform:
        specific_path = get_platform_cookie_path(platform)
        if os.path.exists(specific_path) and os.path.getsize(specific_path) > 0:
            return os.path.abspath(specific_path)

    # Fallback to legacy single file
    if os.path.exists(LEGACY_COOKIES_PATH) and os.path.getsize(LEGACY_COOKIES_PATH) > 0:
        return os.path.abspath(LEGACY_COOKIES_PATH)

    return None


def get_all_cookies_status() -> Dict[str, bool]:
    """Return configured status for all supported platforms and legacy cookies."""
    status: Dict[str, bool] = {}
    for p in SUPPORTED_COOKIE_PLATFORMS:
        p_path = get_platform_cookie_path(p)
        status[p] = os.path.exists(p_path) and os.path.getsize(p_path) > 0

    legacy_exists = os.path.exists(LEGACY_COOKIES_PATH) and os.path.getsize(LEGACY_COOKIES_PATH) > 0
    status["legacy"] = legacy_exists
    # Overall configured is True if any platform or legacy cookie exists
    status["configured"] = any(status.values())
    return status
