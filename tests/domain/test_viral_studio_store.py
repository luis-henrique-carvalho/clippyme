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
        viral_studio_store.get_batch_or_raise("missing-batch")

    with pytest.raises(NotFoundError):
        viral_studio_store.get_item_or_raise("missing-item")
