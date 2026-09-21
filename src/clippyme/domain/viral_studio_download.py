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
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
import uuid

import yt_dlp

from clippyme.domain.errors import DownloadError, ValidationError
from clippyme.netutil import resolve_host_addresses

SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

SUPPORTED_VIRAL_HOSTS = frozenset(
    {
        "instagram.com",
        "www.instagram.com",
        "m.instagram.com",
        "instagr.am",
        "www.instagr.am",
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
_VALID_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi", ".flv", ".ts"})
_IGNORE_DOWNLOAD_EXTENSIONS = frozenset(
    {
        ".part",
        ".ytdl",
        ".tmp",
        ".temp",
        ".json",
        ".txt",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".vtt",
        ".srt",
        ".aria2",
    }
)


def validate_viral_source_url(url: str) -> str:
    """Return a normalized supported URL or raise a domain validation error."""
    if not isinstance(url, str):
        raise ValidationError("Source URL must be a string")
    raw = url.strip()
    if not raw:
        raise ValidationError("Source URL must not be blank")
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in raw):
        raise ValidationError("Source URL contains invalid whitespace or control characters")
    if "%00" in raw.lower():
        raise ValidationError("Source URL contains invalid encoded characters")
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
        or not parsed.path
        or not parsed.path.strip("/")
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
    except (OSError, TimeoutError, UnicodeError, ValueError) as exc:
        raise DownloadError("Could not resolve source host") from exc
    if not addresses:
        raise DownloadError("Source host did not resolve to an address")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if getattr(ip, "ipv4_mapped", None):
            mapped = ip.ipv4_mapped
            if (
                not mapped.is_global
                or mapped.is_private
                or mapped.is_loopback
                or mapped.is_link_local
                or mapped.is_reserved
                or mapped.is_multicast
                or mapped.is_unspecified
            ):
                raise ValidationError("Source URL points to a non-public address")
        if (
            not ip.is_global
            or ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
            or getattr(ip, "is_site_local", False)
        ):
            raise ValidationError("Source URL points to a non-public address")


def _write_manifest(
    output_path: Path,
    source: str,
    *,
    source_kind: str = "remote",
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Persist provenance next to the preserved source without exposing secrets."""
    manifest = {
        "source": source,
        "source_kind": source_kind,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "reusable_for_rerender": True,
        "metadata": metadata or {},
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


def get_source_manifest(source_path: str | Path) -> dict[str, Any]:
    """Read the manifest JSON next to the source file if it exists."""
    manifest_path = Path(source_path).with_name(SOURCE_MANIFEST_FILENAME)
    if manifest_path.is_file():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _find_downloaded_file(directory: Path, prefix: str) -> Path | None:
    candidates = [
        path for path in directory.glob(f"{prefix}*")
        if path.is_file() and path.suffix.lower() not in _IGNORE_DOWNLOAD_EXTENSIONS
    ]
    mp4 = [path for path in candidates if path.suffix.lower() == ".mp4"]
    valid_videos = [path for path in candidates if path.suffix.lower() in _VALID_VIDEO_EXTENSIONS]
    return (mp4 or valid_videos or [None])[0]


def download_viral_video(url: str, output_path: str, timeout: int = 120) -> str:
    """Download a Reel/TikTok into ``output_path`` and retain it for reuse.

    Existing non-empty sources are returned unchanged.  yt-dlp writes to a
    sibling temporary name and the completed media is atomically renamed to the
    caller's canonical ``source.mp4`` path.
    """
    source_url = validate_viral_source_url(url)
    if not output_path or not isinstance(output_path, (str, Path)):
        raise ValidationError("Download output path must be a non-empty string or Path")
    if not isinstance(timeout, int) or not 1 <= timeout <= 600:
        raise ValidationError("Download timeout must be between 1 and 600 seconds")
    destination = Path(output_path)
    if destination.exists() and destination.is_dir():
        raise ValidationError("Download output path must be a file")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DownloadError(f"Could not create download directory: {exc}") from exc
    if destination.is_file() and destination.stat().st_size > 0:
        return str(destination)

    _assert_public_resolution(source_url)
    prefix = f".viral-source-{uuid.uuid4().hex[:8]}-"
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
        extracted_info = None
        with yt_dlp.YoutubeDL(options) as downloader:
            if hasattr(downloader, "extract_info"):
                try:
                    extracted_info = downloader.extract_info(source_url, download=True)
                except Exception:
                    downloader.download([source_url])
            else:
                downloader.download([source_url])
        downloaded = _find_downloaded_file(destination.parent, prefix)
        if downloaded is None or downloaded.stat().st_size == 0:
            raise DownloadError("yt-dlp completed without producing a video file")
        os.replace(downloaded, destination)

        meta_dict = {}
        if isinstance(extracted_info, dict):
            meta_dict = {
                "title": extracted_info.get("title") or "",
                "description": extracted_info.get("description") or "",
                "tags": extracted_info.get("tags") or [],
                "uploader": extracted_info.get("uploader") or "",
                "view_count": extracted_info.get("view_count") or extracted_info.get("play_count") or extracted_info.get("video_view_count"),
                "like_count": extracted_info.get("like_count") or extracted_info.get("likes"),
                "comment_count": extracted_info.get("comment_count") or extracted_info.get("comments"),
                "repost_count": extracted_info.get("repost_count") or extracted_info.get("reposts") or extracted_info.get("share_count"),
            }
        _write_manifest(destination, source_url, metadata=meta_dict)
        return str(destination)
    except (ValidationError, DownloadError):
        raise
    except Exception as exc:
        raise DownloadError(f"Could not download source video: {exc}") from exc
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
    if not upload_path or not isinstance(upload_path, (str, Path)):
        raise ValidationError("Uploaded source path must be a non-empty string or Path")
    if not output_path or not isinstance(output_path, (str, Path)):
        raise ValidationError("Download output path must be a non-empty string or Path")
    source = Path(upload_path)
    destination = Path(output_path)
    if not source.is_file() or source.stat().st_size == 0:
        raise ValidationError("Uploaded source must be a non-empty regular file")
    if destination.exists() and destination.is_dir():
        raise ValidationError("Download output path must be a file")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValidationError(f"Cannot create destination directory: {exc}") from exc
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


def resolve_source_path(batch_id: str, item_id: str, base_dir: str | None = None) -> str:
    """Return the canonical path output/viral_studio/<batch_id>/<item_id>/source.mp4."""
    if not isinstance(batch_id, str) or not SAFE_ID_RE.match(batch_id.strip()):
        raise ValidationError(f"Invalid batch_id: {batch_id!r}")
    if not isinstance(item_id, str) or not SAFE_ID_RE.match(item_id.strip()):
        raise ValidationError(f"Invalid item_id: {item_id!r}")
    if base_dir is not None and not isinstance(base_dir, (str, Path)):
        raise ValidationError("base_dir must be a string or Path")
    clean_batch = batch_id.strip()
    clean_item = item_id.strip()
    root = base_dir or os.environ.get("CLIPPYME_OUTPUT_DIR") or "output"
    return str(Path(root) / "viral_studio" / clean_batch / clean_item / SOURCE_FILENAME)


def download_batch_item(
    batch_id: str,
    item: Any,
    base_dir: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """Download a single batch item's source video into its isolated source.mp4 location.

    If the download fails, isolates the failure by updating the item's status to FAILED
    and recording the error message without raising or affecting other items.
    """
    if not isinstance(item, (dict, Mapping)):
        return {
            "id": "unknown",
            "status": "FAILED",
            "error_message": f"Invalid item payload: expected dict, got {type(item).__name__}",
        }
    updated = dict(item)
    item_id = updated.get("id") or updated.get("item_id")
    source_url = updated.get("source_url")
    if not source_url or not item_id:
        updated["status"] = "FAILED"
        updated["error_message"] = "Missing source_url or item id"
        return updated

    try:
        destination = resolve_source_path(batch_id, str(item_id), base_dir)
        saved_path = download_viral_video(source_url, destination, timeout=timeout)
        updated["source_path"] = saved_path
        manifest = get_source_manifest(saved_path)
        if manifest.get("metadata"):
            updated["source_metadata"] = manifest["metadata"]
        updated["status"] = "READY_FOR_REVIEW"
        updated["error_message"] = None
    except Exception as exc:
        updated["status"] = "FAILED"
        updated["error_message"] = str(exc)
    return updated


def download_batch_items(
    batch_id: str,
    items: list[dict[str, Any]],
    base_dir: str | None = None,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    """Download source videos for a batch of items with strict failure isolation.

    Iterates through each item independently; any failure in one item is trapped
    and sets that item to FAILED with error_message, while all other items continue
    processing normally.
    """
    if not isinstance(items, (list, tuple)):
        return []
    results: list[dict[str, Any]] = []
    for item in items:
        processed = download_batch_item(batch_id, item, base_dir=base_dir, timeout=timeout)
        results.append(processed)
    return results


def process_batch_downloads(
    batch_id: str,
    base_dir: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """Load batch from store, download items with failure isolation, and update store."""
    from clippyme.domain import viral_studio_store

    batch = viral_studio_store.get_batch_or_raise(batch_id)
    items = batch.get("items", [])
    updated_items = download_batch_items(batch_id, items, base_dir=base_dir, timeout=timeout)
    for it in updated_items:
        it_id = it.get("id") or it.get("item_id")
        if it_id:
            viral_studio_store.update_item(it_id, it)
    all_failed = all(it.get("status") == "FAILED" for it in updated_items) if updated_items else False
    new_status = "FAILED" if all_failed else "READY_FOR_REVIEW"
    viral_studio_store.update_batch(batch_id, {"status": new_status})
    return viral_studio_store.get_batch_or_raise(batch_id)
