"""Unit tests for the Viral Content Studio's safe source downloader."""
from __future__ import annotations

from pathlib import Path

import pytest

from clippyme.domain import viral_studio_download as downloader
from clippyme.domain.errors import DownloadError, ValidationError


@pytest.mark.parametrize(
    "url",
    [
        "http://www.instagram.com/reel/abc/",
        "https://instagram.com.evil.test/reel/abc/",
        "https://vimeo.com/12345",
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
        "https://instagr.am/p/shortcode/",
        "https://www.instagr.am/reel/abc/",
        "https://www.tiktok.com/@creator/video/123",
        "https://vm.tiktok.com/short-code/",
        "https://www.youtube.com/shorts/abc123xyz",
        "https://youtu.be/abc123xyz",
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


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://facebook.com/reel/12345",
        "https://twitter.com/i/status/12345",
        "https://vimeo.com/12345",
        "https://evil.com/video.mp4",
        "https://sub.instagram.com.evil.com/video.mp4",
    ],
)
def test_download_rejects_non_allowlisted_domains(bad_url, tmp_path):
    """Rejects domains not in the allowlist."""
    with pytest.raises(ValidationError) as exc_info:
        downloader.download_viral_video(bad_url, str(tmp_path / "source.mp4"))
    assert "source url must be an official https youtube, instagram, or tiktok url" in str(exc_info.value).lower()


@pytest.mark.parametrize(
    "ssrf_url",
    [
        "http://127.0.0.1:8000/source.mp4",
        "http://127.0.0.1/video.mp4",
        "http://localhost:8000/video.mp4",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/video.mp4",
        "http://192.168.1.1/video.mp4",
    ],
)
def test_download_rejects_ssrf_risk_urls(ssrf_url, tmp_path):
    """Rejects URLs targeting internal, localhost, or link-local private IPs."""
    with pytest.raises(ValidationError):
        downloader.download_viral_video(ssrf_url, str(tmp_path / "source.mp4"))


def test_download_preserves_source_file_at_canonical_path(tmp_path, monkeypatch):
    """Verifies downloaded source file is saved at output/viral_studio/<batch_id>/<item_id>/source.mp4."""
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _urls):
            outtmpl = self.options["outtmpl"]
            actual = Path(outtmpl.replace("%(id)s", "vid1").replace("%(ext)s", "mp4"))
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(b"canonical_mp4_bytes")

    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    batch_id = "batch-101"
    item_id = "item-202"
    canonical_path = downloader.resolve_source_path(batch_id, item_id, base_dir=str(tmp_path))

    expected_path = str(tmp_path / "viral_studio" / batch_id / item_id / "source.mp4")
    assert canonical_path == expected_path

    saved = downloader.download_viral_video("https://www.instagram.com/reel/abc1234/", canonical_path)
    assert saved == expected_path
    assert Path(expected_path).is_file()
    assert Path(expected_path).read_bytes() == b"canonical_mp4_bytes"


def test_batch_item_failure_isolation(tmp_path, monkeypatch):
    """Failure of item 2 must NOT affect item 1 or item 3."""
    class SelectiveYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, urls):
            url = urls[0]
            if "fail" in url:
                raise RuntimeError("Video unavailable / private")
            outtmpl = self.options["outtmpl"]
            actual = Path(outtmpl.replace("%(id)s", "test_id").replace("%(ext)s", "mp4"))
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(b"valid_video_bytes")

    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", SelectiveYoutubeDL)

    batch_id = "batch_iso_01"
    items = [
        {"id": "item_1", "source_url": "https://www.instagram.com/reel/good1/", "product_code": "P1"},
        {"id": "item_2", "source_url": "https://www.instagram.com/reel/fail_private/", "product_code": "P2"},
        {"id": "item_3", "source_url": "https://www.tiktok.com/@creator/video/good3", "product_code": "P3"},
    ]

    processed = downloader.download_batch_items(batch_id, items, base_dir=str(tmp_path))

    assert len(processed) == 3
    # Item 1 succeeded
    assert processed[0]["status"] != "FAILED"
    assert processed[0]["status"] == "READY_FOR_REVIEW"
    assert Path(processed[0]["source_path"]).exists()
    assert processed[0]["error_message"] is None

    # Item 2 failed in isolation
    assert processed[1]["status"] == "FAILED"
    assert "could not download" in processed[1]["error_message"].lower() or "video unavailable" in processed[1]["error_message"].lower()

    # Item 3 succeeded despite item 2 failure
    assert processed[2]["status"] != "FAILED"
    assert processed[2]["status"] == "READY_FOR_REVIEW"
    assert Path(processed[2]["source_path"]).exists()
    assert processed[2]["error_message"] is None


@pytest.mark.parametrize("bad_type_url", [123, [], {}, True, None])
def test_validate_viral_source_url_rejects_non_strings(bad_type_url):
    """Rejects non-string inputs with ValidationError rather than AttributeError."""
    with pytest.raises(ValidationError):
        downloader.validate_viral_source_url(bad_type_url)


@pytest.mark.parametrize("bad_path", [None, "", 123])
def test_download_rejects_invalid_output_path(bad_path):
    """Rejects invalid output paths with ValidationError."""
    with pytest.raises(ValidationError):
        downloader.download_viral_video("https://www.instagram.com/reel/abc/", bad_path)


@pytest.mark.parametrize("bad_path", [None, "", 123])
def test_preserve_uploaded_source_rejects_invalid_paths(bad_path, tmp_path):
    """Rejects invalid upload or destination paths with ValidationError."""
    with pytest.raises(ValidationError):
        downloader.preserve_uploaded_source(bad_path, str(tmp_path / "out.mp4"))
    with pytest.raises(ValidationError):
        downloader.preserve_uploaded_source(str(tmp_path / "in.mp4"), bad_path)


@pytest.mark.parametrize(
    "bad_batch,bad_item",
    [
        ("../../etc", "item_1"),
        ("batch_1", "/etc/passwd"),
        ("batch_1", "../item_1"),
        ("batch 1", "item_1"),
        ("batch_1", "item\0bad"),
        ("", "item_1"),
        ("batch_1", ""),
    ],
)
def test_resolve_source_path_rejects_traversal_and_invalid_ids(bad_batch, bad_item):
    """Rejects path traversal, null bytes, and absolute paths in batch_id or item_id."""
    with pytest.raises(ValidationError):
        downloader.resolve_source_path(bad_batch, bad_item)


def test_download_ignores_partial_part_and_ytdl_files(tmp_path, monkeypatch):
    """When yt-dlp produces only a .part or .ytdl file, it must not be promoted to source.mp4."""
    class PartOnlyYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _urls):
            outtmpl = self.options["outtmpl"]
            part_file = Path(outtmpl.replace("%(id)s", "vid1").replace("%(ext)s", "mp4.part"))
            part_file.parent.mkdir(parents=True, exist_ok=True)
            part_file.write_bytes(b"partial_bytes")

    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", PartOnlyYoutubeDL)

    dest = str(tmp_path / "batch" / "item" / "source.mp4")
    with pytest.raises(DownloadError) as exc:
        downloader.download_viral_video("https://www.instagram.com/reel/abc1234/", dest)
    assert "completed without producing a video file" in str(exc.value)
    assert not Path(dest).exists()


def test_batch_item_failure_isolation_with_invalid_item_id(tmp_path, monkeypatch):
    """Item with invalid ID must fail in isolation without crashing the entire batch."""
    class FakeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, urls):
            outtmpl = self.options["outtmpl"]
            actual = Path(outtmpl.replace("%(id)s", "id").replace("%(ext)s", "mp4"))
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(b"vid")

    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeDL)

    batch_id = "safe-batch-01"
    items = [
        {"id": "item-1", "source_url": "https://www.instagram.com/reel/good1/", "product_code": "P1"},
        {"id": "../../traversal-item", "source_url": "https://www.instagram.com/reel/good2/", "product_code": "P2"},
        {"id": "item-3", "source_url": "https://www.tiktok.com/@creator/video/good3", "product_code": "P3"},
    ]

    processed = downloader.download_batch_items(batch_id, items, base_dir=str(tmp_path))

    assert len(processed) == 3
    assert processed[0]["status"] == "READY_FOR_REVIEW"
    assert processed[1]["status"] == "FAILED"
    assert "invalid item_id" in processed[1]["error_message"].lower()
    assert processed[2]["status"] == "READY_FOR_REVIEW"


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://www.instagram.com/reel/abc 123/",
        "https://www.instagram.com/reel/abc\n123/",
        "https://www.instagram.com/reel/abc\r123/",
        "https://www.instagram.com/reel/abc\t123/",
        "https://www.instagram.com/reel/abc%00def/",
    ],
)
def test_validate_viral_source_url_rejects_internal_whitespace_and_control_chars(bad_url):
    """Rejects URLs with internal whitespace, newlines, carriage returns, or null bytes."""
    with pytest.raises(ValidationError):
        downloader.validate_viral_source_url(bad_url)


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://www.instagram.com",
        "https://www.instagram.com/",
        "https://www.tiktok.com",
        "https://www.tiktok.com/",
        "https://instagram.com#@evil.com/reel/123",
        "https://instagram.com?@evil.com/reel/123",
    ],
)
def test_validate_viral_source_url_rejects_empty_path_and_fragment_confusion(bad_url):
    """Rejects root domain URLs and fragment/query parser confusion tricks with empty path."""
    with pytest.raises(ValidationError):
        downloader.validate_viral_source_url(bad_url)


@pytest.mark.parametrize(
    "blocked_ip",
    [
        "100.64.0.1",       # CGNAT (RFC 6598)
        "fec0::1",          # IPv6 site-local (RFC 3879)
        "2001:db8::1",      # IPv6 documentation (RFC 3849)
        "::ffff:10.0.0.1",  # IPv4-mapped private
        "::ffff:127.0.0.1", # IPv4-mapped loopback
    ],
)
def test_assert_public_resolution_rejects_cgnat_and_special_ipv6(tmp_path, monkeypatch, blocked_ip):
    """Rejects CGNAT, IPv6 site-local, and mapped private addresses in DNS resolution."""
    monkeypatch.setattr(downloader, "resolve_host_addresses", lambda *_args, **_kwargs: [blocked_ip])
    with pytest.raises(ValidationError) as exc:
        downloader.download_viral_video("https://www.instagram.com/reel/abc1234/", str(tmp_path / "source.mp4"))
    assert "non-public" in str(exc.value).lower()


def test_assert_public_resolution_wraps_resolver_exceptions(tmp_path, monkeypatch):
    """DNS resolver errors like ValueError are wrapped in DownloadError."""
    def raise_value_error(*_args, **_kwargs):
        raise ValueError("Malformed DNS response")

    monkeypatch.setattr(downloader, "resolve_host_addresses", raise_value_error)
    with pytest.raises(DownloadError) as exc:
        downloader.download_viral_video("https://www.instagram.com/reel/abc1234/", str(tmp_path / "source.mp4"))
    assert "could not resolve" in str(exc.value).lower()


def test_download_ignores_metadata_and_thumbnail_files(tmp_path, monkeypatch):
    """yt-dlp producing only .info.json and .jpg must not promote them to source.mp4."""
    class MetaOnlyYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _urls):
            outtmpl = self.options["outtmpl"]
            info_file = Path(outtmpl.replace("%(id)s", "vid1").replace("%(ext)s", "info.json"))
            thumb_file = Path(outtmpl.replace("%(id)s", "vid1").replace("%(ext)s", "jpg"))
            info_file.parent.mkdir(parents=True, exist_ok=True)
            info_file.write_text('{"title": "test"}')
            thumb_file.write_bytes(b"fake_jpg")

    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", MetaOnlyYoutubeDL)

    dest = str(tmp_path / "batch" / "item" / "source.mp4")
    with pytest.raises(DownloadError) as exc:
        downloader.download_viral_video("https://www.instagram.com/reel/abc1234/", dest)
    assert "completed without producing a video file" in str(exc.value)
    assert not Path(dest).exists()


def test_batch_item_failure_isolation_with_non_dict_payload(tmp_path, monkeypatch):
    """Non-dict items (None, string, int) in batch must fail in isolation without crashing the batch."""
    class FakeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, urls):
            outtmpl = self.options["outtmpl"]
            actual = Path(outtmpl.replace("%(id)s", "id").replace("%(ext)s", "mp4"))
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(b"vid")

    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeDL)

    batch_id = "safe-batch-non-dict"
    items = [
        {"id": "item-1", "source_url": "https://www.instagram.com/reel/good1/"},
        None,
        "invalid-string-payload",
        {"id": "item-4", "source_url": "https://www.tiktok.com/@creator/video/good4"},
    ]

    processed = downloader.download_batch_items(batch_id, items, base_dir=str(tmp_path))

    assert len(processed) == 4
    assert processed[0]["status"] == "READY_FOR_REVIEW"
    assert processed[1]["status"] == "FAILED"
    assert "invalid item payload" in processed[1]["error_message"].lower()
    assert processed[2]["status"] == "FAILED"
    assert "invalid item payload" in processed[2]["error_message"].lower()
    assert processed[3]["status"] == "READY_FOR_REVIEW"


def test_download_batch_items_handles_none_or_non_sequence(tmp_path):
    """download_batch_items returns empty list for None or non-sequence items."""
    assert downloader.download_batch_items("batch-1", None, base_dir=str(tmp_path)) == []
    assert downloader.download_batch_items("batch-1", 123, base_dir=str(tmp_path)) == []


def test_download_handles_directory_creation_failure(tmp_path, monkeypatch):
    """When output path parent cannot be created because a parent is a file, DownloadError is raised."""
    parent_file = tmp_path / "not_a_dir"
    parent_file.write_text("i am a file")
    dest = str(parent_file / "subdir" / "source.mp4")

    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    with pytest.raises(DownloadError) as exc:
        downloader.download_viral_video("https://www.instagram.com/reel/good1/", dest)
    assert "could not create download directory" in str(exc.value).lower()


def test_process_batch_downloads_advances_batch_status(tmp_path, monkeypatch):
    """process_batch_downloads updates batch status to READY_FOR_REVIEW on success or FAILED on all-fail."""
    from clippyme.domain import viral_studio_store

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(viral_studio_store, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(viral_studio_store, "BRANDS_FILE", str(data_dir / "brands.json"))
    monkeypatch.setattr(viral_studio_store, "TEMPLATES_FILE", str(data_dir / "templates.json"))
    monkeypatch.setattr(viral_studio_store, "BATCHES_FILE", str(data_dir / "batches.json"))
    monkeypatch.setattr(viral_studio_store, "ITEMS_FILE", str(data_dir / "items.json"))

    class FakeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, urls):
            if "fail" in urls[0]:
                raise RuntimeError("Failed video")
            outtmpl = self.options["outtmpl"]
            actual = Path(outtmpl.replace("%(id)s", "id").replace("%(ext)s", "mp4"))
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(b"vid")

    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeDL)

    # 1. Successful batch
    batch_ok = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {"source_url": "https://www.instagram.com/reel/good1/"},
            {"source_url": "https://www.instagram.com/reel/good2/"},
        ],
    })
    b_id = batch_ok["id"]
    res_ok = downloader.process_batch_downloads(b_id, base_dir=str(tmp_path))
    assert res_ok["status"] == "READY_FOR_REVIEW"

    # 2. All-fail batch
    batch_fail = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {"source_url": "https://www.instagram.com/reel/fail1/"},
            {"source_url": "https://www.instagram.com/reel/fail2/"},
        ],
    })
    b_fail_id = batch_fail["id"]
    res_fail = downloader.process_batch_downloads(b_fail_id, base_dir=str(tmp_path))
    assert res_fail["status"] == "FAILED"


def test_download_injects_platform_cookies(tmp_path, monkeypatch):
    """Verifies that platform cookies are resolved and passed to YoutubeDL options."""
    cookies_dir = tmp_path / "data" / "cookies"
    cookies_dir.mkdir(parents=True, exist_ok=True)
    yt_cookie = cookies_dir / "youtube.txt"
    yt_cookie.write_text("# Netscape HTTP Cookie File\n")

    captured_options = []

    class FakeDL:
        def __init__(self, options):
            self.options = options
            captured_options.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _urls):
            outtmpl = self.options["outtmpl"]
            actual = Path(outtmpl.replace("%(id)s", "yt_vid").replace("%(ext)s", "mp4"))
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(b"yt_video_bytes")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeDL)

    dest = str(tmp_path / "source.mp4")
    downloader.download_viral_video("https://www.youtube.com/shorts/0vO_Fo6-lCQ", dest)

    assert len(captured_options) >= 1
    assert "cookiefile" in captured_options[0]
    assert captured_options[0]["cookiefile"].endswith("youtube.txt")
    assert captured_options[0]["extractor_args"] == {
        "youtube": {"player_client": ["android", "ios", "web_creator", "mweb"]}
    }


def test_download_youtube_403_fallback_loop_succeeds(tmp_path, monkeypatch):
    """When attempt 1 fails with 403 Forbidden, attempt 2 with alternate player_client succeeds."""
    attempts = []

    class FallbackYoutubeDL:
        def __init__(self, options):
            self.options = options
            attempts.append(options.get("extractor_args"))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _urls):
            if len(attempts) == 1:
                raise RuntimeError("HTTP Error 403: Forbidden")
            outtmpl = self.options["outtmpl"]
            actual = Path(outtmpl.replace("%(id)s", "yt_vid").replace("%(ext)s", "mp4"))
            actual.parent.mkdir(parents=True, exist_ok=True)
            actual.write_bytes(b"downloaded_on_retry")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(downloader, "_assert_public_resolution", lambda _url: None)
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FallbackYoutubeDL)

    dest = str(tmp_path / "source.mp4")
    res = downloader.download_viral_video("https://www.youtube.com/shorts/0vO_Fo6-lCQ", dest)

    assert res == dest
    assert Path(dest).read_bytes() == b"downloaded_on_retry"
    assert len(attempts) == 2



