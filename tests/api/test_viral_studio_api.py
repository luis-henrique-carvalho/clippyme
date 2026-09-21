import os
import pytest
from fastapi.testclient import TestClient

import clippyme.api.app as app_module
import clippyme.domain.viral_studio_store as store_module

ORIGIN = {"Origin": "http://localhost:5175"}


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    """TestClient with temporary directory for viral studio store and outputs."""
    data_dir = tmp_path / "viral_studio"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CLIPPYME_OUTPUT_DIR", str(out_dir))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(out_dir))
    monkeypatch.setattr(store_module, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(store_module, "BRANDS_FILE", None)
    monkeypatch.setattr(store_module, "TEMPLATES_FILE", None)
    monkeypatch.setattr(store_module, "BATCHES_FILE", None)
    monkeypatch.setattr(store_module, "ITEMS_FILE", None)
    return TestClient(app_module.app, headers=ORIGIN)


def test_cors_patch_preflight(api_client):
    """Verify CORS preflight succeeds for PATCH requests."""
    resp = api_client.options(
        "/api/viral-studio/brands/vale-o-clique",
        headers={
            "Origin": "http://localhost:5175",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert resp.status_code == 200
    allow_methods = resp.headers.get("access-control-allow-methods", "")
    assert "PATCH" in allow_methods


def test_list_brands_default_seed(api_client):
    """GET /api/viral-studio/brands returns seeded default brand."""
    resp = api_client.get("/api/viral-studio/brands")
    assert resp.status_code == 200
    data = resp.json()
    assert "brands" in data
    assert "total" in data
    assert data["total"] >= 1
    assert any(b["id"] == "vale-o-clique" for b in data["brands"])


def test_create_and_get_brand(api_client):
    """POST creates brand (201) and GET /brands/{id} retrieves it."""
    payload = {
        "id": "florzinha-ofertas",
        "name": "Ofertas da Florzinha",
        "handle": "@florzinha",
        "default_cta": "Veja os achadinhos!",
        "template_id": "classic-affiliate",
    }
    create_resp = api_client.post("/api/viral-studio/brands", json=payload)
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["id"] == "florzinha-ofertas"
    assert created["name"] == "Ofertas da Florzinha"
    assert created["handle"] == "@florzinha"

    # Fetch by ID
    get_resp = api_client.get("/api/viral-studio/brands/florzinha-ofertas")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == "florzinha-ofertas"


def test_create_duplicate_brand_returns_409(api_client):
    """POST with an existing brand ID returns 409 Conflict."""
    payload = {
        "id": "unique-brand-id",
        "name": "Brand Once",
        "handle": "@brand1",
        "template_id": "classic-affiliate",
    }
    r1 = api_client.post("/api/viral-studio/brands", json=payload)
    assert r1.status_code == 201

    r2 = api_client.post("/api/viral-studio/brands", json=payload)
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"].lower()


def test_patch_brand(api_client):
    """PATCH /brands/{id} updates only specified fields."""
    api_client.post(
        "/api/viral-studio/brands",
        json={
            "id": "patch-brand",
            "name": "Before Name",
            "handle": "@before",
            "template_id": "classic-affiliate",
        },
    )

    patch_resp = api_client.patch(
        "/api/viral-studio/brands/patch-brand",
        json={"name": "After Name", "handle": "@after"},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["name"] == "After Name"
    assert updated["handle"] == "@after"


def test_patch_nonexistent_brand_returns_404(api_client):
    """PATCH on a non-existent brand returns 404 Not Found."""
    resp = api_client.patch(
        "/api/viral-studio/brands/nonexistent-brand-id",
        json={"name": "Does Not Matter"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_nonexistent_brand_returns_404(api_client):
    """GET on a non-existent brand returns 404 Not Found."""
    resp = api_client.get("/api/viral-studio/brands/missing-brand-12345")
    assert resp.status_code == 404


def test_list_templates(api_client):
    """GET /api/viral-studio/templates returns default classic-affiliate template."""
    resp = api_client.get("/api/viral-studio/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert "templates" in data
    assert any(t["id"] == "classic-affiliate" for t in data["templates"])
    classic = next(t for t in data["templates"] if t["id"] == "classic-affiliate")
    assert classic["width"] == 1080
    assert classic["height"] == 1920


def test_get_template_by_id(api_client):
    """GET /api/viral-studio/templates/{id} retrieves specific template."""
    resp = api_client.get("/api/viral-studio/templates/classic-affiliate")
    assert resp.status_code == 200
    assert resp.json()["id"] == "classic-affiliate"


def test_get_nonexistent_template_returns_404(api_client):
    """GET /api/viral-studio/templates/{id} with invalid ID returns 404."""
    resp = api_client.get("/api/viral-studio/templates/invalid-template-xyz")
    assert resp.status_code == 404


def test_create_brand_path_traversal_rejected(api_client):
    """Asset paths containing '..' traversal are rejected."""
    payload = {
        "id": "traversal-brand",
        "name": "Traversal Brand",
        "handle": "@traversal",
        "avatar_path": "../../../etc/passwd",
    }
    resp = api_client.post("/api/viral-studio/brands", json=payload)
    assert resp.status_code in (400, 422)


def test_create_brand_ssrf_rejected(api_client):
    """Affiliate URL pointing to internal private IP is rejected."""
    payload = {
        "id": "ssrf-brand-test",
        "name": "SSRF Brand",
        "handle": "@ssrfbrand",
        "default_affiliate_url": "http://127.0.0.1:8000/steal",
    }
    resp = api_client.post("/api/viral-studio/brands", json=payload)
    assert resp.status_code in (400, 422)


def test_create_and_get_template(api_client):
    """POST creates template (201) and GET /templates/{id} retrieves it."""
    payload = {
        "id": "minimal-dark",
        "name": "Minimal Dark",
        "width": 1080,
        "height": 1920,
        "background_color": "#000000",
        "headline_color": "#FFFFFF",
        "video_fit": "cover",
    }
    create_resp = api_client.post("/api/viral-studio/templates", json=payload)
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["id"] == "minimal-dark"
    assert created["name"] == "Minimal Dark"
    assert created["background_color"] == "#000000"
    assert created["headline_color"] == "#FFFFFF"
    assert created["video_fit"] == "cover"
    assert created["created_at"] is not None
    assert created["updated_at"] is not None

    # Fetch by ID
    get_resp = api_client.get("/api/viral-studio/templates/minimal-dark")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["id"] == "minimal-dark"
    assert fetched["name"] == "Minimal Dark"
    assert fetched["background_color"] == "#000000"


def test_create_duplicate_template_returns_409(api_client):
    """POST with an existing template ID returns 409 Conflict."""
    payload = {
        "id": "unique-template-id",
        "name": "Template Once",
        "background_color": "#FFFFFF",
    }
    r1 = api_client.post("/api/viral-studio/templates", json=payload)
    assert r1.status_code == 201

    r2 = api_client.post("/api/viral-studio/templates", json=payload)
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"].lower()


def test_patch_template(api_client):
    """PATCH /templates/{id} updates only specified fields."""
    api_client.post(
        "/api/viral-studio/templates",
        json={
            "id": "patch-template",
            "name": "Before Template",
            "background_color": "#FFFFFF",
            "video_fit": "contain",
        },
    )

    patch_resp = api_client.patch(
        "/api/viral-studio/templates/patch-template",
        json={"name": "After Template", "background_color": "#1A1A1A", "video_fit": "cover"},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["id"] == "patch-template"
    assert updated["name"] == "After Template"
    assert updated["background_color"] == "#1A1A1A"
    assert updated["video_fit"] == "cover"

    # Verify persistence via GET
    get_resp = api_client.get("/api/viral-studio/templates/patch-template")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["name"] == "After Template"
    assert fetched["background_color"] == "#1A1A1A"


def test_patch_nonexistent_template_returns_404(api_client):
    """PATCH on a non-existent template returns 404 Not Found."""
    resp = api_client.patch(
        "/api/viral-studio/templates/nonexistent-template-id",
        json={"name": "Does Not Matter"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_create_brand_auto_slugify_id(api_client):
    """POST /brands without id automatically slugifies name into id."""
    payload = {
        "name": "Achadinhos da Luíza & Cia",
        "handle": "@luiza",
    }
    resp = api_client.post("/api/viral-studio/brands", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "achadinhos-da-luiza-cia"
    assert data["name"] == "Achadinhos da Luíza & Cia"
    assert data["handle"] == "@luiza"

    # Verify retrieval
    get_resp = api_client.get("/api/viral-studio/brands/achadinhos-da-luiza-cia")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == "achadinhos-da-luiza-cia"


def test_create_template_auto_slugify_id(api_client):
    """POST /templates without id automatically slugifies name into id."""
    payload = {
        "name": "Minimalist Dark Mode",
        "background_color": "#000000",
    }
    resp = api_client.post("/api/viral-studio/templates", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "minimalist-dark-mode"
    assert data["name"] == "Minimalist Dark Mode"

    # Verify retrieval
    get_resp = api_client.get("/api/viral-studio/templates/minimalist-dark-mode")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == "minimalist-dark-mode"


def test_create_brand_absolute_path_rejected(api_client):
    """Absolute paths like /etc/passwd and C:\\Windows are rejected with 422."""
    bad_paths = [
        "/etc/passwd",
        "/root/.ssh/id_rsa",
        "C:\\Windows\\System32\\cmd.exe",
        "\\\\attacker\\share\\pic.png",
        "file:///etc/passwd",
    ]
    for bad in bad_paths:
        payload = {
            "name": "Exploit Brand",
            "handle": "@exploit",
            "avatar_path": bad,
        }
        resp = api_client.post("/api/viral-studio/brands", json=payload)
        assert resp.status_code in (400, 422), f"Expected 400/422 for path {bad}, got {resp.status_code}"


def test_patch_brand_absolute_path_rejected(api_client):
    """PATCH with absolute avatar path returns 422."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "patch-path-brand", "name": "Patch Path", "handle": "@patchpath"},
    )
    resp = api_client.patch(
        "/api/viral-studio/brands/patch-path-brand",
        json={"avatar_path": "/etc/shadow"},
    )
    assert resp.status_code in (400, 422)


def test_create_brand_disallowed_prefix_rejected(api_client):
    """Disallowed relative prefixes and hidden files return 422."""
    for bad in ["var/log/syslog", ".env", "uploads/.git/config"]:
        resp = api_client.post(
            "/api/viral-studio/brands",
            json={"name": "Bad Prefix", "handle": "@badprefix", "avatar_path": bad},
        )
        assert resp.status_code in (400, 422)


def test_create_brand_safe_asset_paths_accepted(api_client):
    """Allowed prefixes (uploads/, data/) and safe filenames are accepted."""
    safe_samples = [
        ("uploads/brands/florzinha/avatar.png", "b-safe-1"),
        ("data/logo.png", "b-safe-2"),
        ("avatar.png", "b-safe-3"),
    ]
    for path, brand_id in safe_samples:
        resp = api_client.post(
            "/api/viral-studio/brands",
            json={"id": brand_id, "name": f"Safe {brand_id}", "handle": f"@{brand_id}", "avatar_path": path},
        )
        assert resp.status_code == 201, f"Failed for path {path}: {resp.text}"
        assert resp.json()["avatar_path"] == path


def test_create_batch_returns_201_with_pending_items(api_client):
    """POST /api/viral-studio/batches with 3 items returns 201 and items in PENDING state."""
    # Ensure brand exists
    api_client.post(
        "/api/viral-studio/brands",
        json={
            "id": "batch-brand-201",
            "name": "Batch Brand 201",
            "handle": "@batchbrand201",
            "template_id": "classic-affiliate",
        },
    )

    batch_payload = {
        "brand_id": "batch-brand-201",
        "items": [
            {
                "source_url": "https://www.instagram.com/reel/C_ITEM1/",
                "product_code": "PROD_1",
                "product_url": "https://example.com/item1",
                "manual_headline": "Headline 1",
            },
            {
                "source_url": "https://www.tiktok.com/@creator/video/123456",
                "product_code": "PROD_2",
                "additional_instructions": "Highlight ease of use",
            },
            {
                "source_url": "https://vm.tiktok.com/shortcode3/",
                "product_code": "PROD_3",
            },
        ],
    }
    resp = api_client.post("/api/viral-studio/batches", json=batch_payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert "id" in data
    assert "batch_id" in data
    assert data["id"] == data["batch_id"]
    assert data["brand_id"] == "batch-brand-201"
    assert data["status"] == "PENDING"
    assert data["total_items"] == 3
    assert len(data["items"]) == 3

    for idx, item in enumerate(data["items"]):
        assert item["id"] is not None
        assert item["batch_id"] == data["id"]
        assert item["brand_id"] == "batch-brand-201"
        assert item["status"] == "PENDING"
        assert item["error_message"] is None
        assert item["created_at"] is not None
        assert item["updated_at"] is not None

    assert data["items"][0]["product_code"] == "PROD_1"
    assert data["items"][1]["product_code"] == "PROD_2"
    assert data["items"][2]["product_code"] == "PROD_3"


def test_get_batch_by_id(api_client):
    """GET /api/viral-studio/batches/{id} returns batch metadata and per-item status."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "get-batch-brand", "name": "Get Batch Brand", "handle": "@getbatch"},
    )
    create_resp = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "get-batch-brand",
            "items": [
                {"source_url": "https://www.instagram.com/reel/C_GET1/", "product_code": "G1"},
                {"source_url": "https://www.tiktok.com/@creator/video/789", "product_code": "G2"},
            ],
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    batch_id = created["id"]

    get_resp = api_client.get(f"/api/viral-studio/batches/{batch_id}")
    assert get_resp.status_code == 200
    fetched = get_resp.json()
    assert fetched["id"] == batch_id
    assert fetched["brand_id"] == "get-batch-brand"
    assert fetched["total_items"] == 2
    assert len(fetched["items"]) == 2
    assert fetched["items"][0]["status"] in ("PENDING", "DOWNLOADING", "FAILED", "READY_FOR_REVIEW")
    assert fetched["items"][1]["status"] in ("PENDING", "DOWNLOADING", "FAILED", "READY_FOR_REVIEW")


def test_get_item_by_id(api_client):
    """GET /api/viral-studio/items/{id} returns individual item metadata."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "item-query-brand", "name": "Item Query Brand", "handle": "@itemquery"},
    )
    create_resp = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "item-query-brand",
            "items": [
                {"source_url": "https://www.instagram.com/reel/C_SINGLE/", "product_code": "SINGLE_01"},
            ],
        },
    )
    assert create_resp.status_code == 201
    item_id = create_resp.json()["items"][0]["id"]

    item_resp = api_client.get(f"/api/viral-studio/items/{item_id}")
    assert item_resp.status_code == 200
    item_data = item_resp.json()
    assert item_data["id"] == item_id
    assert item_data["brand_id"] == "item-query-brand"
    assert item_data["product_code"] == "SINGLE_01"
    assert item_data["status"] in ("PENDING", "DOWNLOADING", "FAILED", "READY_FOR_REVIEW")


def test_create_batch_empty_items_rejected(api_client):
    """POST /api/viral-studio/batches with empty items list returns 422."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "empty-items-brand", "name": "Empty Items Brand", "handle": "@emptyitems"},
    )
    resp = api_client.post(
        "/api/viral-studio/batches",
        json={"brand_id": "empty-items-brand", "items": []},
    )
    assert resp.status_code in (400, 422)


def test_create_batch_invalid_url_rejected(api_client):
    """POST /api/viral-studio/batches with non-allowlisted domain returns 422."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "bad-url-brand", "name": "Bad URL Brand", "handle": "@badurl"},
    )
    resp = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "bad-url-brand",
            "items": [{"source_url": "https://vimeo.com/12345"}],
        },
    )
    assert resp.status_code in (400, 422)


def test_create_batch_ssrf_url_rejected(api_client):
    """POST /api/viral-studio/batches with private IP source URL returns 422."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "ssrf-batch-brand", "name": "SSRF Batch Brand", "handle": "@ssrfbatch"},
    )
    for bad_ssrf in ["http://127.0.0.1:8000/exploit", "http://169.254.169.254/meta"]:
        resp = api_client.post(
            "/api/viral-studio/batches",
            json={
                "brand_id": "ssrf-batch-brand",
                "items": [{"source_url": bad_ssrf}],
            },
        )
        assert resp.status_code in (400, 422)


def test_create_batch_ssrf_product_url_rejected(api_client):
    """POST /api/viral-studio/batches with private IP product_url returns 422."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "ssrf-prod-brand", "name": "SSRF Prod Brand", "handle": "@ssrfprod"},
    )
    resp = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "ssrf-prod-brand",
            "items": [
                {
                    "source_url": "https://www.instagram.com/reel/C_OKAY/",
                    "product_url": "http://127.0.0.1:8000/internal",
                }
            ],
        },
    )
    assert resp.status_code in (400, 422)


def test_create_batch_nonexistent_brand_returns_404(api_client):
    """POST /api/viral-studio/batches with unknown brand_id returns 404."""
    resp = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "brand-does-not-exist-at-all",
            "items": [{"source_url": "https://www.instagram.com/reel/C_OKAY/"}],
        },
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_nonexistent_batch_returns_404(api_client):
    """GET /api/viral-studio/batches/{id} with missing ID returns 404."""
    resp = api_client.get("/api/viral-studio/batches/missing-batch-99999")
    assert resp.status_code == 404


def test_get_nonexistent_item_returns_404(api_client):
    """GET /api/viral-studio/items/{id} with missing ID returns 404."""
    resp = api_client.get("/api/viral-studio/items/missing-item-99999")
    assert resp.status_code == 404


def test_list_batches(api_client):
    """GET /api/viral-studio/batches returns all created batches."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "list-batches-brand", "name": "List Batches", "handle": "@listbatches"},
    )
    api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "list-batches-brand",
            "items": [{"source_url": "https://www.instagram.com/reel/C_BATCH1/"}],
        },
    )
    resp = api_client.get("/api/viral-studio/batches")
    assert resp.status_code == 200
    data = resp.json()
    assert "batches" in data
    assert data["total"] >= 1
    assert any(b["brand_id"] == "list-batches-brand" for b in data["batches"])


def test_create_batch_whitespace_brand_id_rejected(api_client):
    """POST /api/viral-studio/batches with whitespace-only brand_id returns 422."""
    resp = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "   ",
            "items": [{"source_url": "https://www.instagram.com/reel/C_BATCH1/"}],
        },
    )
    assert resp.status_code in (400, 422)


def test_create_batch_nonexistent_template_returns_404(api_client):
    """POST /api/viral-studio/batches with missing template_id returns 404."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "valid-b-id", "name": "Valid Brand", "handle": "@validb"},
    )
    resp = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "valid-b-id",
            "template_id": "nonexistent-tmpl-99999",
            "items": [{"source_url": "https://www.instagram.com/reel/C_BATCH1/"}],
        },
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_patch_item(api_client):
    """PATCH /api/viral-studio/items/{id} updates commercial fields."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "patch-item-brand", "name": "Patch Item Brand", "handle": "@patchitem"},
    )
    b = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "patch-item-brand",
            "items": [{"source_url": "https://www.instagram.com/reel/C_PATCH_ITEM/", "product_code": "OLD_CODE"}],
        },
    ).json()
    item_id = b["items"][0]["id"]

    resp = api_client.patch(
        f"/api/viral-studio/items/{item_id}",
        json={
            "selected_headline": "Nova Headline Atualizada! 😱",
            "caption": "Legenda atualizada com sucesso!\n#publi",
            "product_code": "NEW_CODE_99",
        },
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["id"] == item_id
    assert updated["selected_headline"] == "Nova Headline Atualizada! 😱"
    assert updated["caption"] == "Legenda atualizada com sucesso!\n#publi"
    assert updated["product_code"] == "NEW_CODE_99"


def test_create_batch_and_patch_item_with_model(api_client):
    """POST /api/viral-studio/batches with model propagates to items and allows PATCH model."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "model-test-brand", "name": "Model Brand", "handle": "@modelbrand"},
    )
    b_resp = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "model-test-brand",
            "model": "ollama:llama3.2",
            "items": [
                {"source_url": "https://www.instagram.com/reel/C_MODEL_1/"},
                {"source_url": "https://www.instagram.com/reel/C_MODEL_2/", "model": "gemini:gemini-3.6-flash"},
            ],
        },
    )
    assert b_resp.status_code == 201, b_resp.text
    b = b_resp.json()
    assert b["model"] == "ollama:llama3.2"
    assert b["items"][0]["model"] == "ollama:llama3.2"
    assert b["items"][1]["model"] == "gemini:gemini-3.6-flash"

    # Patch first item with different model
    item_id = b["items"][0]["id"]
    patch_resp = api_client.patch(
        f"/api/viral-studio/items/{item_id}",
        json={"model": "gemini:gemini-3.5-flash-lite"},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["model"] == "gemini:gemini-3.5-flash-lite"



def test_patch_nonexistent_item_returns_404(api_client):
    """PATCH /api/viral-studio/items/{id} on missing item returns 404."""
    resp = api_client.patch(
        "/api/viral-studio/items/nonexistent-item-9999",
        json={"selected_headline": "Should Fail"},
    )
    assert resp.status_code == 404


def test_patch_item_cannot_change_lifecycle_status(api_client):
    api_client.post("/api/viral-studio/brands", json={"id": "state-guard", "name": "State Guard", "handle": "@state"})
    batch = api_client.post("/api/viral-studio/batches", json={
        "brand_id": "state-guard", "items": [{"source_url": "https://www.instagram.com/reel/C_STATE/"}],
    }).json()
    response = api_client.patch(
        f"/api/viral-studio/items/{batch['items'][0]['id']}", json={"status": "APPROVED"},
    )
    assert response.status_code == 422


def test_render_item_endpoint(api_client, monkeypatch, tmp_path):
    """POST /api/viral-studio/items/{id}/render queues a durable re-render."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "render-api-brand", "name": "Render API Brand", "handle": "@renderapi"},
    )
    b = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "render-api-brand",
            "items": [{"source_url": "https://www.instagram.com/reel/C_RENDER_API/"}],
        },
    ).json()
    item_id = b["items"][0]["id"]
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source video")
    store_module.update_item(item_id, {"source_path": str(source), "job_id": None, "status": "READY_FOR_REVIEW"})

    resp = api_client.post(
        f"/api/viral-studio/items/{item_id}/render",
        json={"headline": "Headline para Renderizar! ✨"},
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["id"] == item_id
    assert data["status"] == "RENDERING"
    assert data["job_id"] is not None


def test_approve_item_endpoint(api_client, monkeypatch, tmp_path):
    """POST /api/viral-studio/items/{id}/approve transitions item to APPROVED."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "approve-api-brand", "name": "Approve API Brand", "handle": "@approveapi"},
    )
    b = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "approve-api-brand",
            "items": [{"source_url": "https://www.instagram.com/reel/C_APPROVE_API/"}],
        },
    ).json()
    item_id = b["items"][0]["id"]

    rendered_file = tmp_path / "rendered.mp4"
    rendered_file.write_bytes(b"dummy video")

    # Mark item ready for review with rendered path
    store_module.update_item(item_id, {"status": "READY_FOR_REVIEW", "rendered_path": str(rendered_file)})

    resp = api_client.post(f"/api/viral-studio/items/{item_id}/approve")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == item_id
    assert data["status"] == "APPROVED"


def test_approve_unrendered_item_returns_400(api_client):
    """POST /api/viral-studio/items/{id}/approve on unrendered item returns 400."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "unrendered-api-brand", "name": "Unrendered Brand", "handle": "@unrenderedapi"},
    )
    b = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "unrendered-api-brand",
            "items": [{"source_url": "https://www.instagram.com/reel/C_UNRENDERED/"}],
        },
    ).json()
    item_id = b["items"][0]["id"]

    resp = api_client.post(f"/api/viral-studio/items/{item_id}/approve")
    assert resp.status_code in (400, 422)


def test_retry_item_endpoint(api_client):
    """POST /api/viral-studio/items/{id}/retry resets status to PENDING."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "retry-api-brand", "name": "Retry API Brand", "handle": "@retryapi"},
    )
    b = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "retry-api-brand",
            "items": [{"source_url": "https://www.instagram.com/reel/C_RETRY/"}],
        },
    ).json()
    item_id = b["items"][0]["id"]

    store_module.update_item(item_id, {"status": "FAILED", "error_message": "Previous error"})

    resp = api_client.post(f"/api/viral-studio/items/{item_id}/retry")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == item_id
    assert data["status"] == "PENDING"
    assert data["error_message"] is None


def test_publish_items_endpoint(api_client, monkeypatch, tmp_path):
    """POST /api/viral-studio/publish publishes approved items."""
    api_client.post(
        "/api/viral-studio/brands",
        json={"id": "pub-api-brand", "name": "Pub API Brand", "handle": "@pubapi"},
    )
    b = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "pub-api-brand",
            "items": [{"source_url": "https://www.instagram.com/reel/C_PUB_API/"}],
        },
    ).json()
    item_id = b["items"][0]["id"]

    rendered_file = tmp_path / "rendered.mp4"
    rendered_file.write_bytes(b"dummy video")

    store_module.update_item(item_id, {"status": "APPROVED", "rendered_path": str(rendered_file)})

    async def fake_publish(**kwargs):
        return {
            "status": "published",
            "post_id": "post_12345",
            "platform_post_id": "plat_12345",
            "published_at": "2026-09-19T18:00:00Z",
        }

    monkeypatch.setattr("clippyme.domain.publish_service.publish_clip_flow", fake_publish)

    resp = api_client.post(
        "/api/viral-studio/publish",
        json={
            "item_ids": [item_id],
            "platforms": [{"platform": "instagram", "accountId": "ig_acc_1"}],
            "schedule_mode": "now",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["successful"] == 1
    assert data["failed"] == 0
    assert data["results"][0]["status"] == "published"
    assert data["results"][0]["post_id"] == "post_12345"


def test_get_batch_and_item_includes_context_and_logs(api_client):
    """GET /batches/{id} and GET /items/{id} serialize logs, source_metadata, and ai_context_summary."""
    brand = api_client.post(
        "/api/viral-studio/brands",
        json={"id": "logs-brand", "name": "Logs Brand", "handle": "@logsbrand"},
    ).json()

    batch_resp = api_client.post(
        "/api/viral-studio/batches",
        json={
            "brand_id": "logs-brand",
            "items": [{"source_url": "https://www.instagram.com/reel/C_LOGS_API/"}],
        },
    )
    assert batch_resp.status_code == 201
    batch = batch_resp.json()
    item_id = batch["items"][0]["id"]

    # Update item with source_metadata, ai_context_summary, and logs
    store_module.update_item(
        item_id,
        {
            "source_metadata": {"title": "Post Title", "description": "Original caption"},
            "ai_context_summary": {"scenes_count": 3, "keyframes_count": 3, "has_audio": True},
            "logs": [{"stage": "INIT", "message": "Initialized", "timestamp": "2026-09-20T18:00:00Z"}],
        },
    )

    item_resp = api_client.get(f"/api/viral-studio/items/{item_id}")
    assert item_resp.status_code == 200
    item_data = item_resp.json()
    assert item_data["source_metadata"]["title"] == "Post Title"
    assert item_data["ai_context_summary"]["scenes_count"] == 3
    assert len(item_data["logs"]) == 1
    assert item_data["logs"][0]["stage"] == "INIT"

    # Also verify batch endpoint returns it in the item list
    batch_get = api_client.get(f"/api/viral-studio/batches/{batch['id']}")
    assert batch_get.status_code == 200
    item_in_batch = batch_get.json()["items"][0]
    assert item_in_batch["ai_context_summary"]["scenes_count"] == 3
    assert len(item_in_batch["logs"]) == 1


