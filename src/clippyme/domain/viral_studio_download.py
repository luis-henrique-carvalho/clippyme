"""Safe, reusable source-video ingestion for Viral Content Studio.

This module deliberately owns the remote-input boundary.  It accepts only
public Instagram Reels and TikTok URLs, checks DNS immediately before invoking
yt-dlp, and keeps the resulting ``source.mp4`` intact for later re-renders.
"""
from __future__ import annotations

import ipaddress
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yt_dlp

from clippyme.domain.errors import DownloadError, ValidationError
from clippyme.netutil import resolve_host_addresses

SUPPORTED_VIRAL_HOSTS = frozenset(
    {
        "instagram.com",
        "www.instagram.com",
        "m.instagram.com",
        "tiktok.com",
        "www.tiktok.com",
        "m.tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
    }
)
SOURCE_FILENAME = "source.mp4"
SOURCE_MANIFEST_FILENAME = "source_manifest.json"
_FORMAT_LADDER = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"


def validate_viral_source_url(url: str) -> str:
    """Return a normalized supported URL or raise a domain validation error."""
    raw = (url or "").strip()
    try:
        parsed = urlparse(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("Invalid source URL") from exc
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in SUPPORTED_VIRAL_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ValidationError("Source URL must be an official HTTPS Instagram or TikTok URL")
    return raw


def _assert_public_resolution(url: str) -> None:
    """Refuse a supported host if its current DNS answer is non-public."""
    host = urlparse(url).hostname
    if not host:  # guarded by validate_viral_source_url; defensive for direct use
        raise ValidationError("Source URL has no host")
    try:
        addresses = resolve_host_addresses(host, timeout=5.0)
    except (OSError, TimeoutError, UnicodeError) as exc:
        raise DownloadError("Could not resolve source host") from exc
    if not addresses:
        raise DownloadError("Source host did not resolve to an address")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValidationError("Source URL points to a non-public address")


def _write_manifest(output_path: Path, source: str, *, source_kind: str = "remote") -> None:
    """Persist provenance next to the preserved source without exposing secrets."""
    manifest = {
        "source": source,
        "source_kind": source_kind,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "reusable_for_rerender": True,
    }
    manifest_path = output_path.with_name(SOURCE_MANIFEST_FILENAME)
    fd, temp_path = tempfile.mkstemp(prefix=".source_manifest-", suffix=".tmp", dir=output_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, manifest_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _find_downloaded_file(directory: Path, prefix: str) -> Path | None:
    candidates = [path for path in directory.glob(f"{prefix}*") if path.is_file()]
    mp4 = [path for path in candidates if path.suffix.lower() == ".mp4"]
    return (mp4 or candidates or [None])[0]


def download_viral_video(url: str, output_path: str, timeout: int = 120) -> str:
    """Download a Reel/TikTok into ``output_path`` and retain it for reuse.

    Existing non-empty sources are returned unchanged.  yt-dlp writes to a
    sibling temporary name and the completed media is atomically renamed to the
    caller's canonical ``source.mp4`` path.
    """
    source_url = validate_viral_source_url(url)
    if not isinstance(timeout, int) or not 1 <= timeout <= 600:
        raise ValidationError("Download timeout must be between 1 and 600 seconds")
    destination = Path(output_path)
    if destination.exists() and destination.is_dir():
        raise ValidationError("Download output path must be a file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        return str(destination)

    _assert_public_resolution(source_url)
    prefix = ".viral-source-"
    options: dict[str, Any] = {
        "format": _FORMAT_LADDER,
        "outtmpl": str(destination.parent / f"{prefix}%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": timeout,
        "retries": 3,
        "fragment_retries": 3,
        "overwrites": True,
        "cachedir": False,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.download([source_url])
        downloaded = _find_downloaded_file(destination.parent, prefix)
        if downloaded is None or downloaded.stat().st_size == 0:
            raise DownloadError("yt-dlp completed without producing a video file")
        os.replace(downloaded, destination)
        _write_manifest(destination, source_url)
        return str(destination)
    except (ValidationError, DownloadError):
        raise
    except Exception as exc:
        raise DownloadError("Could not download source video") from exc
    finally:
        for candidate in destination.parent.glob(f"{prefix}*"):
            if candidate.is_file():
                try:
                    candidate.unlink()
                except OSError:
                    pass


def preserve_uploaded_source(upload_path: str, output_path: str) -> str:
    """Atomically preserve an already-validated server-side upload as source.mp4.

    The HTTP layer is responsible for size and media validation while streaming
    the upload.  This helper only accepts a regular, non-empty local file and
    copies it into the item's durable source location without retaining a
    partially copied file on failure.
    """
    source = Path(upload_path)
    destination = Path(output_path)
    if not source.is_file() or source.stat().st_size == 0:
        raise ValidationError("Uploaded source must be a non-empty regular file")
    if destination.exists() and destination.is_dir():
        raise ValidationError("Download output path must be a file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        return str(destination)

    fd, temp_path = tempfile.mkstemp(prefix=".viral-upload-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as target, source.open("rb") as uploaded:
            shutil.copyfileobj(uploaded, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp_path, destination)
        _write_manifest(destination, source.name, source_kind="upload")
        return str(destination)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
