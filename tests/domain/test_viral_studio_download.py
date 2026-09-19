"""Unit tests for the Viral Content Studio's safe source downloader."""
from __future__ import annotations

from pathlib import Path

import pytest

from clippyme.domain.errors import DownloadError, ValidationError
from clippyme.domain import viral_studio_download as downloader


@pytest.mark.parametrize(
    "url",
    [
        "http://www.instagram.com/reel/abc/",
        "https://instagram.com.evil.test/reel/abc/",
        "https://www.youtube.com/watch?v=abc",
        "https://user:pass@www.tiktok.com/@user/video/1",
        "file:///etc/passwd",
    ],
)
def test_validate_viral_source_url_rejects_untrusted_urls(url):
    with pytest.raises(ValidationError):
        downloader.validate_viral_source_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/reel/abc/",
        "https://www.tiktok.com/@creator/video/123",
        "https://vm.tiktok.com/short-code/",
    ],
)
def test_validate_viral_source_url_accepts_supported_platforms(url):
    assert downloader.validate_viral_source_url(url) == url


def test_download_preserves_existing_source_without_network(tmp_path, monkeypatch):
    target = tmp_path / "source.mp4"
    target.write_bytes(b"existing source")
    monkeypatch.setattr(
        downloader, "_assert_public_resolution", lambda _url: pytest.fail("network must not run")
    )
    assert downloader.download_viral_video("https://www.instagram.com/reel/abc/", str(target)) == str(target)
    assert target.read_bytes() == b"existing source"


def test_download_atomically_promotes_source_and_records_provenance(tmp_path, monkeypatch):
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _urls):
            Path(self.options["outtmpl"].replace("%(id)s", "abc").replace("%(ext)s", "mp4")).write_bytes(b"video")

    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    target = tmp_path / "batch" / "item" / "source.mp4"

    assert downloader.download_viral_video("https://www.tiktok.com/@creator/video/123", str(target)) == str(target)
    assert target.read_bytes() == b"video"
    assert '"reusable_for_rerender": true' in (target.parent / downloader.SOURCE_MANIFEST_FILENAME).read_text()


def test_download_rejects_private_dns_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, "resolve_host_addresses", lambda *_args, **_kwargs: ["127.0.0.1"])
    with pytest.raises(ValidationError):
        downloader.download_viral_video("https://www.instagram.com/reel/abc/", str(tmp_path / "source.mp4"))


def test_preserve_uploaded_source_atomically_and_reuses_destination(tmp_path):
    upload = tmp_path / "uploaded.mp4"
    upload.write_bytes(b"uploaded video")
    target = tmp_path / "batch" / "item" / "source.mp4"

    assert downloader.preserve_uploaded_source(str(upload), str(target)) == str(target)
    assert target.read_bytes() == b"uploaded video"
    assert '"source_kind": "upload"' in (target.parent / downloader.SOURCE_MANIFEST_FILENAME).read_text()

    upload.write_bytes(b"a later upload must not overwrite the preserved source")
    assert downloader.preserve_uploaded_source(str(upload), str(target)) == str(target)
    assert target.read_bytes() == b"uploaded video"


def test_preserve_uploaded_source_rejects_empty_or_missing_file(tmp_path):
    empty = tmp_path / "empty.mp4"
    empty.touch()
    with pytest.raises(ValidationError):
        downloader.preserve_uploaded_source(str(empty), str(tmp_path / "source.mp4"))
    with pytest.raises(ValidationError):
        downloader.preserve_uploaded_source(str(tmp_path / "missing.mp4"), str(tmp_path / "source.mp4"))


def test_download_wraps_ytdlp_failure(tmp_path, monkeypatch):
    class BrokenYoutubeDL:
        def __init__(self, _options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _urls):
            raise RuntimeError("unavailable")

    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", BrokenYoutubeDL)
    with pytest.raises(DownloadError):
        downloader.download_viral_video("https://www.instagram.com/reel/abc/", str(tmp_path / "source.mp4"))
