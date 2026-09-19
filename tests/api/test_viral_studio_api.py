"""Unit and contract tests for Viral Content Studio REST API (Milestone 1)."""
import pytest
from fastapi.testclient import TestClient

import clippyme.api.app as app_module
import clippyme.domain.viral_studio_store as store_module

ORIGIN = {"Origin": "http://localhost:5175"}


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    """TestClient with temporary directory for viral studio store."""
    data_dir = tmp_path / "viral_studio"
    data_dir.mkdir(parents=True, exist_ok=True)
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

