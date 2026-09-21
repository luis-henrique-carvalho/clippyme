"""Unit tests for viral_studio_store (Milestone 1 persistence)."""
import os
import threading
from unittest.mock import patch

import pytest

from clippyme.domain import viral_studio_store
from clippyme.domain.errors import ConflictError, NotFoundError, ValidationError


@pytest.fixture
def tmp_store(tmp_path):
    store_dir = str(tmp_path / "viral_studio")
    viral_studio_store.set_store_dir(store_dir)
    yield store_dir
    viral_studio_store.reset_store()


def test_default_seeds_initialization(tmp_store):
    brands = viral_studio_store.list_brands()
    assert len(brands) == 1
    assert brands[0]["id"] == "vale-o-clique"
    assert brands[0]["name"] == "Vale o Clique?"

    templates = viral_studio_store.list_templates()
    assert len(templates) == 1
    assert templates[0]["id"] == "classic-affiliate"
    assert templates[0]["width"] == 1080
    assert templates[0]["height"] == 1920


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions only")
def test_owner_only_permissions(tmp_store):
    viral_studio_store.list_brands()
    st_dir = os.stat(tmp_store).st_mode & 0o777
    assert st_dir == 0o700
    st_file = os.stat(viral_studio_store.get_brands_path()).st_mode & 0o777
    assert st_file == 0o600


def test_atomic_write_cleans_up_on_failure(tmp_store):
    with patch("os.replace", side_effect=OSError("Disk full")), pytest.raises(OSError):
        viral_studio_store._atomic_write_json(
            viral_studio_store.get_brands_path(), {"test": 1}
        )
    # Ensure no leftover .tmp files
    files = os.listdir(tmp_store)
    assert not any(f.endswith(".tmp") for f in files)


def test_corrupt_json_resilience(tmp_store):
    path = viral_studio_store.get_brands_path()
    os.makedirs(tmp_store, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{corrupt json...")

    # Reading should not raise; it re-seeds the default brand
    brands = viral_studio_store.list_brands()
    assert len(brands) == 1
    assert brands[0]["id"] == "vale-o-clique"


def test_brand_crud(tmp_store):
    b = viral_studio_store.create_brand({
        "id": "my-brand",
        "name": "My Brand",
        "handle": "@mybrand",
        "default_cta": "Click link",
        "template_id": "classic-affiliate",
    })
    assert b["id"] == "my-brand"
    assert b["created_at"] is not None

    fetched = viral_studio_store.get_brand("my-brand")
    assert fetched is not None
    assert fetched["name"] == "My Brand"

    updated = viral_studio_store.update_brand("my-brand", {"name": "New Brand Name"})
    assert updated["name"] == "New Brand Name"
    assert updated["handle"] == "@mybrand"

    assert viral_studio_store.delete_brand("my-brand") is True
    assert viral_studio_store.get_brand("my-brand") is None


def test_create_brand_conflict(tmp_store):
    viral_studio_store.create_brand({
        "id": "brand-conflict-test",
        "name": "First Creation",
        "handle": "@first",
    })
    with pytest.raises(ConflictError):
        viral_studio_store.create_brand({
            "id": "brand-conflict-test",
            "name": "Duplicate Creation",
            "handle": "@second",
        })


def test_update_brand_not_found(tmp_store):
    with pytest.raises(NotFoundError):
        viral_studio_store.update_brand("nonexistent", {"name": "Updated"})


def test_template_crud(tmp_store):
    t = viral_studio_store.create_template({
        "id": "custom-tmpl",
        "name": "Custom Template",
        "background_color": "#000000",
    })
    assert t["id"] == "custom-tmpl"

    fetched = viral_studio_store.get_template("custom-tmpl")
    assert fetched is not None
    assert fetched["background_color"] == "#000000"

    updated = viral_studio_store.update_template("custom-tmpl", {"background_color": "#222222"})
    assert updated["background_color"] == "#222222"

    assert viral_studio_store.delete_template("custom-tmpl") is True
    assert viral_studio_store.get_template("custom-tmpl") is None


def test_batches_and_items_lifecycle(tmp_store):
    batch = viral_studio_store.create_batch({
        "batch_id": "b_001",
        "brand_id": "vale-o-clique",
        "status": "PENDING",
        "items": [
            {
                "id": "item_1",
                "source_url": "https://instagram.com/reel/123",
                "product_code": "PROD_A",
                "status": "PENDING",
            }
        ],
    })
    assert batch["batch_id"] == "b_001"

    item = viral_studio_store.get_item("item_1")
    assert item is not None
    assert item["product_code"] == "PROD_A"
    assert item["batch_id"] == "b_001"

    updated = viral_studio_store.update_item("item_1", {
        "status": "ANALYZING",
        "selected_headline": "Promo headline",
    })
    assert updated["status"] == "ANALYZING"
    assert updated["selected_headline"] == "Promo headline"

    # Verify parent batch contains mutated item
    b = viral_studio_store.get_batch("b_001")
    assert b["items"][0]["status"] == "ANALYZING"


def test_concurrent_access(tmp_store):
    def worker(tid):
        for i in range(10):
            viral_studio_store.create_brand({
                "id": f"t_{tid}_b_{i}",
                "name": f"Brand {tid}_{i}",
                "handle": f"@b_{tid}_{i}",
            })

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 1 default + 50 created = 51 brands
    assert len(viral_studio_store.list_brands()) == 51


def test_validation_errors(tmp_store):
    with pytest.raises(ValidationError):
        viral_studio_store.create_brand({"handle": "@nohandle"})

    with pytest.raises(ValidationError):
        viral_studio_store.create_brand({})

    with pytest.raises(ValidationError):
        viral_studio_store.update_brand("", {"name": "Blank ID"})

    with pytest.raises(ValidationError):
        viral_studio_store.create_template({"width": 1080})

    with pytest.raises(ValidationError):
        viral_studio_store.create_template({})

    with pytest.raises(ValidationError):
        viral_studio_store.create_batch({"brand_id": "some-brand"})


def test_create_brand_and_template_auto_derives_id_from_name(tmp_store):
    """Omitting id auto-derives identifier slug from name."""
    brand = viral_studio_store.create_brand({
        "name": "Achadinhos da Luíza & Cia",
        "handle": "@luiza",
    })
    assert brand["id"] == "achadinhos-da-luiza-cia"
    assert brand["name"] == "Achadinhos da Luíza & Cia"

    # Fetch to confirm persistence
    fetched_b = viral_studio_store.get_brand("achadinhos-da-luiza-cia")
    assert fetched_b is not None
    assert fetched_b["id"] == "achadinhos-da-luiza-cia"

    template = viral_studio_store.create_template({
        "name": "Dark Mode Neon!",
        "background_color": "#000000",
    })
    assert template["id"] == "dark-mode-neon"
    assert template["name"] == "Dark Mode Neon!"

    # Fetch to confirm persistence
    fetched_t = viral_studio_store.get_template("dark-mode-neon")
    assert fetched_t is not None
    assert fetched_t["id"] == "dark-mode-neon"


def test_brand_asset_path_validation(tmp_store):
    """Absolute paths, traversal, hidden files, and null bytes are rejected in store."""
    bad_paths = [
        "/etc/passwd",
        "/root/.ssh/id_rsa",
        "C:\\Windows\\System32\\cmd.exe",
        "\\\\attacker\\share\\pic.png",
        "file:///etc/passwd",
        "../../../etc/passwd",
        "uploads/../../etc/passwd",
        ".env",
        "uploads/.git/config",
        "var/log/syslog",
        "avatar\0.png",
        "avatar%00.png",
        "uploads/",
    ]
    for bad in bad_paths:
        with pytest.raises(ValidationError):
            viral_studio_store.create_brand({
                "id": f"bad-{abs(hash(bad))}",
                "name": "Bad Path Brand",
                "handle": "@badpath",
                "avatar_path": bad,
            })

    # Also verify update_brand rejects bad paths
    viral_studio_store.create_brand({
        "id": "good-b",
        "name": "Good Brand",
        "handle": "@goodb",
    })
    for bad in bad_paths:
        with pytest.raises(ValidationError):
            viral_studio_store.update_brand("good-b", {"avatar_path": bad})
        with pytest.raises(ValidationError):
            viral_studio_store.update_brand("good-b", {"logo_path": bad})


def test_brand_safe_asset_paths_accepted(tmp_store):
    """Safe relative paths and filenames are accepted in store."""
    safe_paths = [
        "uploads/brands/avatar.png",
        "data/brand_logo.jpg",
        "avatar.png",
        None,
    ]
    for i, path in enumerate(safe_paths):
        brand = viral_studio_store.create_brand({
            "id": f"safe-brand-{i}",
            "name": f"Safe Brand {i}",
            "handle": f"@safe{i}",
            "avatar_path": path,
        })
        assert brand["avatar_path"] == path


def test_get_or_raise_not_found(tmp_store):
    with pytest.raises(NotFoundError):
        viral_studio_store.get_brand_or_raise("missing-brand")

    with pytest.raises(NotFoundError):
        viral_studio_store.get_template_or_raise("missing-template")

    with pytest.raises(NotFoundError):
        viral_studio_store.get_item_or_raise("missing-item")


def test_create_batch_rejects_nonexistent_template(tmp_store):
    """create_batch with invalid template_id raises NotFoundError."""
    with pytest.raises(NotFoundError):
        viral_studio_store.create_batch({
            "brand_id": "vale-o-clique",
            "template_id": "does-not-exist-xyz",
            "items": [{"source_url": "https://www.instagram.com/reel/abc/"}],
        })


def test_create_batch_rejects_empty_item_source_url(tmp_store):
    """create_batch with missing or blank source_url on item raises ValidationError."""
    with pytest.raises(ValidationError):
        viral_studio_store.create_batch({
            "brand_id": "vale-o-clique",
            "items": [{"source_url": "   "}],
        })


def test_update_item_clears_error_message_on_recovery(tmp_store):
    """update_item must allow setting error_message=None when an item recovers."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [{"source_url": "https://www.instagram.com/reel/abc/"}],
    })
    item_id = batch["items"][0]["id"]

    # Fail the item
    viral_studio_store.update_item(item_id, {"status": "FAILED", "error_message": "Network failed"})
    failed_item = viral_studio_store.get_item(item_id)
    assert failed_item["status"] == "FAILED"
    assert failed_item["error_message"] == "Network failed"

    # Recover and clear error_message
    viral_studio_store.update_item(item_id, {"status": "READY_FOR_REVIEW", "error_message": None})
    recovered_item = viral_studio_store.get_item(item_id)
    assert recovered_item["status"] == "READY_FOR_REVIEW"
    assert recovered_item["error_message"] is None


def test_create_batch_deduplicates_colliding_item_ids(tmp_store):
    """Items in the same batch with duplicate IDs are given unique UUIDs."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {"id": "duplicate-id", "source_url": "https://www.instagram.com/reel/item1/"},
            {"id": "duplicate-id", "source_url": "https://www.instagram.com/reel/item2/"},
        ],
    })
    ids = [it["id"] for it in batch["items"]]
    assert len(ids) == 2
    assert ids[0] != ids[1]


@pytest.mark.parametrize("bad_batch_id", ["../../etc", "/etc/passwd", "batch 123", "batch\0bad"])
def test_create_batch_rejects_invalid_batch_id(tmp_store, bad_batch_id):
    """create_batch rejects invalid or traversal batch_id with ValidationError."""
    with pytest.raises(ValidationError):
        viral_studio_store.create_batch({
            "brand_id": "vale-o-clique",
            "batch_id": bad_batch_id,
            "items": [{"source_url": "https://www.instagram.com/reel/abc/"}],
        })


@pytest.mark.parametrize("bad_item_id", ["../../etc", "/etc/passwd", "item 123", "item\0bad"])
def test_create_batch_rejects_invalid_item_id(tmp_store, bad_item_id):
    """create_batch rejects invalid or traversal item_id with ValidationError."""
    with pytest.raises(ValidationError):
        viral_studio_store.create_batch({
            "brand_id": "vale-o-clique",
            "items": [{"id": bad_item_id, "source_url": "https://www.instagram.com/reel/abc/"}],
        })


def test_create_batch_rejects_non_dict_item(tmp_store):
    """create_batch rejects non-dict items in items array with ValidationError."""
    with pytest.raises(ValidationError):
        viral_studio_store.create_batch({
            "brand_id": "vale-o-clique",
            "items": ["not_a_dict"],
        })


def test_batch_status_syncs_with_item_status(tmp_store):
    """Batch status automatically derives from item statuses and updates on item change."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {"source_url": "https://www.instagram.com/reel/1/"},
            {"source_url": "https://www.instagram.com/reel/2/"},
        ],
    })
    batch_id = batch["id"]
    item1_id = batch["items"][0]["id"]
    item2_id = batch["items"][1]["id"]

    # Initial state is PENDING
    assert viral_studio_store.get_batch(batch_id)["status"] == "PENDING"
    assert viral_studio_store.list_batches()[0]["status"] == "PENDING"

    # One item completes -> still PENDING since item2 is PENDING
    viral_studio_store.update_item(item1_id, {"status": "READY_FOR_REVIEW"})
    assert viral_studio_store.get_batch(batch_id)["status"] == "PENDING"

    # Both items ready -> READY_FOR_REVIEW
    viral_studio_store.update_item(item2_id, {"status": "READY_FOR_REVIEW"})
    assert viral_studio_store.get_batch(batch_id)["status"] == "READY_FOR_REVIEW"
    assert viral_studio_store.list_batches()[0]["status"] == "READY_FOR_REVIEW"

    # All items failed -> FAILED
    viral_studio_store.update_item(item1_id, {"status": "FAILED"})
    viral_studio_store.update_item(item2_id, {"status": "FAILED"})
    assert viral_studio_store.get_batch(batch_id)["status"] == "FAILED"


def _mp_worker_update_item(store_dir: str, item_id: str, index: int) -> None:
    from clippyme.domain import viral_studio_store
    viral_studio_store.set_store_dir(store_dir)
    viral_studio_store.append_item_log(item_id, {
        "stage": "INIT",
        "message": f"Process {index} start",
    })
    viral_studio_store.update_item(item_id, {
        "status": "READY_FOR_REVIEW",
        "rendered_path": f"/app/output/item_{index}/rendered.mp4",
        "selected_headline": f"Headline {index}",
    })
    viral_studio_store.append_item_log(item_id, {
        "stage": "COMPLETE",
        "message": f"Process {index} done",
    })


def test_cross_process_concurrent_item_updates(tmp_store):
    """Multiple concurrent worker processes updating different items must not overwrite each other."""
    import multiprocessing
    item_count = 6
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {"source_url": f"https://www.instagram.com/reel/proc_{i}/"}
            for i in range(item_count)
        ],
    })
    batch_id = batch["id"]
    item_ids = [it["id"] for it in batch["items"]]

    ctx = multiprocessing.get_context("spawn")
    processes = [
        ctx.Process(target=_mp_worker_update_item, args=(tmp_store, item_ids[i], i))
        for i in range(item_count)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=15)
        assert not p.is_alive()
        assert p.exitcode == 0

    # Validate that every single item's update was safely preserved
    refreshed_batch = viral_studio_store.get_batch(batch_id)
    assert refreshed_batch["status"] == "READY_FOR_REVIEW"
    for i, it in enumerate(refreshed_batch["items"]):
        assert it["status"] == "READY_FOR_REVIEW"
        assert it["rendered_path"] == f"/app/output/item_{i}/rendered.mp4"
        assert it["selected_headline"] == f"Headline {i}"
        stages = [log["stage"] for log in it.get("logs", [])]
        assert "INIT" in stages
        assert "COMPLETE" in stages


def test_store_lock_reentrancy(tmp_store):
    """store_lock must be safely reentrant without deadlocking."""
    with viral_studio_store.store_lock():
        with viral_studio_store.store_lock():
            brands = viral_studio_store.list_brands()
            assert len(brands) >= 1
            with viral_studio_store._STORE_LOCK:
                templates = viral_studio_store.list_templates()
                assert len(templates) >= 1


def test_append_item_log_atomic(tmp_store):
    """append_item_log atomically adds logs and updates item/batch timestamps."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [{"source_url": "https://www.instagram.com/reel/atomic_log/"}],
    })
    item_id = batch["items"][0]["id"]
    logs = viral_studio_store.append_item_log(item_id, {
        "stage": "TEST_STAGE",
        "message": "Atomic log test message",
    })
    assert len(logs) == 1
    assert logs[0]["stage"] == "TEST_STAGE"
    assert logs[0]["message"] == "Atomic log test message"

    item = viral_studio_store.get_item(item_id)
    assert len(item["logs"]) == 1
    assert item["logs"][0]["stage"] == "TEST_STAGE"


