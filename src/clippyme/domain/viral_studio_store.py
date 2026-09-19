"""Atomic JSON file persistence for Viral Content Studio (Brands, Templates, Batches).

Crash-safe storage adhering to ClippyMe standards:
* Atomic writes using sibling temporary files via ``tempfile.mkstemp()`` and ``os.replace()``
* Durability via ``os.fsync()`` on the file descriptor and parent directory descriptor
* Owner-only permissions (0o700 directories, 0o600 files)
* Single re-entrant lock (``threading.RLock``) protecting reads, mutations, and file I/O
* Default seeding of 'vale-o-clique' brand and 'classic-affiliate' template
* Domain error raising (NotFoundError, ConflictError, ValidationError) mapped by API layer
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import pathlib
import re
import tempfile
import threading
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from clippyme.domain.errors import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger("clippyme.viral_studio_store")

SAFE_ASSET_PREFIXES = ("uploads/", "data/")
SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def _slugify(text: str) -> str:
    """Convert arbitrary text to a URL/identifier-safe slug (max 64 chars)."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", text).strip("-_")[:64].rstrip("-_") or "unnamed"


def validate_safe_asset_path(v: Optional[str]) -> Optional[str]:
    """Validate that asset path is safe: no absolute paths, no traversal, allowed prefix or filename."""
    if v is None:
        return None
    raw = str(v).strip()
    if not raw:
        return None

    if "\0" in raw or "%00" in raw.lower():
        raise ValidationError("Null bytes are not permitted in asset paths")

    # Reject absolute paths (POSIX root, Windows drive or backslash root, UNC shares, URL schemes)
    if (
        raw.startswith(("/", "\\"))
        or pathlib.PurePosixPath(raw).is_absolute()
        or pathlib.PureWindowsPath(raw).is_absolute()
        or os.path.isabs(raw)
        or bool(re.match(r"^[a-zA-Z]:", raw))
        or bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw))
    ):
        raise ValidationError("Absolute paths are not permitted in asset paths")

    normalized = raw.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]

    if ".." in parts:
        raise ValidationError("Path traversal ('..') is not permitted in asset paths")

    for part in parts:
        if part.startswith(".") and part != ".":
            raise ValidationError("Hidden files or directories are not permitted in asset paths")

    if normalized.startswith(SAFE_ASSET_PREFIXES):
        if normalized.endswith("/"):
            raise ValidationError("Asset path cannot be a directory")
        return normalized
    elif "/" not in normalized:
        if not SAFE_FILENAME_RE.match(normalized) or normalized in (".", ".."):
            raise ValidationError("Invalid asset filename")
        return normalized
    else:
        raise ValidationError(
            f"Asset path must start with an allowed prefix ({SAFE_ASSET_PREFIXES!r}) or be a relative filename"
        )

DATA_DIR = os.environ.get("CLIPPYME_VIRAL_STUDIO_DIR") or os.path.join("data", "viral_studio")
BRANDS_FILENAME = "brands.json"
TEMPLATES_FILENAME = "templates.json"
BATCHES_FILENAME = "batches.json"

# Overrides for test isolation / monkeypatching
BRANDS_FILE: Optional[str] = None
TEMPLATES_FILE: Optional[str] = None
BATCHES_FILE: Optional[str] = None
ITEMS_FILE: Optional[str] = None

_STORE_LOCK = threading.RLock()

# Default Seeds
DEFAULT_BRAND_ID = "vale-o-clique"
DEFAULT_TEMPLATE_ID = "classic-affiliate"

DEFAULT_TEMPLATE_DICT: Dict[str, Any] = {
    "id": DEFAULT_TEMPLATE_ID,
    "name": "Classic Affiliate",
    "width": 1080,
    "height": 1920,
    "background_color": "#FFFFFF",
    "avatar_enabled": True,
    "brand_name_enabled": True,
    "headline_enabled": True,
    "watermark_enabled": True,
    "video_fit": "contain",
    "avatar_x": 60,
    "avatar_y": 80,
    "avatar_size": 100,
    "brand_name_font_size": 36,
    "brand_name_color": "#111111",
    "handle_font_size": 26,
    "handle_color": "#666666",
    "headline_font_size": 48,
    "headline_color": "#111111",
    "headline_max_lines": 3,
    "headline_margin_x": 60,
    "headline_margin_top": 30,
    "watermark_opacity": 0.7,
    "watermark_position": "bottom-right",
    "created_at": "2026-09-19T00:00:00Z",
    "updated_at": "2026-09-19T00:00:00Z",
}

DEFAULT_BRAND_DICT: Dict[str, Any] = {
    "id": DEFAULT_BRAND_ID,
    "name": "Vale o Clique?",
    "handle": "@valeoclique",
    "avatar_path": None,
    "logo_path": None,
    "default_cta": "Confira os achadinhos no link da bio!",
    "default_affiliate_url": None,
    "template_id": DEFAULT_TEMPLATE_ID,
    "publishing_profiles": {},
    "created_at": "2026-09-19T00:00:00Z",
    "updated_at": "2026-09-19T00:00:00Z",
    "_is_seed": True,
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    raise ValueError(f"Cannot serialize object of type {type(obj)} to dict")


def get_store_dir() -> str:
    return DATA_DIR


def set_store_dir(directory: str) -> None:
    global DATA_DIR, BRANDS_FILE, TEMPLATES_FILE, BATCHES_FILE, ITEMS_FILE
    DATA_DIR = directory
    BRANDS_FILE = None
    TEMPLATES_FILE = None
    BATCHES_FILE = None
    ITEMS_FILE = None


def get_brands_path() -> str:
    return BRANDS_FILE or os.path.join(DATA_DIR, BRANDS_FILENAME)


def get_templates_path() -> str:
    return TEMPLATES_FILE or os.path.join(DATA_DIR, TEMPLATES_FILENAME)


def get_batches_path() -> str:
    return BATCHES_FILE or os.path.join(DATA_DIR, BATCHES_FILENAME)


def _atomic_write_json(file_path: str, data: Dict[str, Any]) -> None:
    """Durably and atomically replace target JSON file with owner-only (0o600) permissions."""
    directory = os.path.dirname(file_path) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(directory, 0o700)

    prefix = f".{os.path.basename(file_path)}-"
    fd, tmp_path = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        with contextlib.suppress(OSError):
            os.chmod(tmp_path, 0o600)

        os.replace(tmp_path, file_path)
        tmp_path = None

        with contextlib.suppress(OSError):
            os.chmod(file_path, 0o600)

        # Persist directory entry on POSIX filesystems
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            except OSError:
                pass
            finally:
                os.close(dir_fd)
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        raise
    finally:
        if tmp_path and os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.remove(tmp_path)


def _read_json_file(file_path: str) -> Dict[str, Any]:
    """Read a JSON dictionary file; return empty dict if missing or corrupt."""
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("Error reading %s: %s", file_path, exc)
        return {}


# ---------------------------------------------------------------------------
# Brand Storage Operations
# ---------------------------------------------------------------------------

def _load_brands_locked() -> Dict[str, Dict[str, Any]]:
    path = get_brands_path()
    brands = _read_json_file(path)
    if not brands:
        brands = {DEFAULT_BRAND_ID: dict(DEFAULT_BRAND_DICT)}
        _atomic_write_json(path, brands)
    return brands


def list_brands() -> List[Dict[str, Any]]:
    with _STORE_LOCK:
        brands = _load_brands_locked()
        res = []
        for b in brands.values():
            item = dict(b)
            item.pop("_is_seed", None)
            res.append(item)
        return sorted(res, key=lambda b: (b.get("name") or b.get("id", "")).lower())


def get_brand(brand_id: str) -> Optional[Dict[str, Any]]:
    if not brand_id:
        return None
    with _STORE_LOCK:
        brands = _load_brands_locked()
        brand = brands.get(brand_id)
        if not brand:
            return None
        res = dict(brand)
        res.pop("_is_seed", None)
        return res


def get_brand_or_raise(brand_id: str) -> Dict[str, Any]:
    brand = get_brand(brand_id)
    if brand is None:
        raise NotFoundError(f"Brand not found: {brand_id}")
    return brand


def create_brand(brand: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    data = _to_dict(brand)
    brand_id = data.get("id")
    if not brand_id or (isinstance(brand_id, str) and not brand_id.strip()):
        name = data.get("name")
        if not name or (isinstance(name, str) and not name.strip()):
            raise ValidationError("Brand id or name is required")
        brand_id = _slugify(name)
        data["id"] = brand_id

    if "avatar_path" in data and data["avatar_path"] is not None:
        data["avatar_path"] = validate_safe_asset_path(data["avatar_path"])
    if "logo_path" in data and data["logo_path"] is not None:
        data["logo_path"] = validate_safe_asset_path(data["logo_path"])

    with _STORE_LOCK:
        brands = _load_brands_locked()
        if brand_id in brands:
            existing = brands[brand_id]
            if existing.get("_is_seed"):
                # Replacing placeholder seed with genuine user brand
                pass
            else:
                raise ConflictError(f"Brand already exists: {brand_id}")

        now = _utcnow_iso()
        data.setdefault("created_at", now)
        data["updated_at"] = now
        data.pop("_is_seed", None)

        brands[brand_id] = data
        _atomic_write_json(get_brands_path(), brands)
        return dict(data)


def update_brand(brand_id: str, updates: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    if not brand_id:
        raise ValidationError("Brand id is required")
    patch = _to_dict(updates)

    if "avatar_path" in patch and patch["avatar_path"] is not None:
        patch["avatar_path"] = validate_safe_asset_path(patch["avatar_path"])
    if "logo_path" in patch and patch["logo_path"] is not None:
        patch["logo_path"] = validate_safe_asset_path(patch["logo_path"])

    with _STORE_LOCK:
        brands = _load_brands_locked()
        if brand_id not in brands:
            raise NotFoundError(f"Brand not found: {brand_id}")

        existing = brands[brand_id]
        for k, v in patch.items():
            if k in ("id", "created_at", "_is_seed"):
                continue
            if v is not None:
                existing[k] = v

        existing["updated_at"] = _utcnow_iso()
        existing.pop("_is_seed", None)
        brands[brand_id] = existing
        _atomic_write_json(get_brands_path(), brands)
        res = dict(existing)
        return res


def save_brand(brand: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    data = _to_dict(brand)
    brand_id = data.get("id")
    if not brand_id or (isinstance(brand_id, str) and not brand_id.strip()):
        name = data.get("name")
        if not name or (isinstance(name, str) and not name.strip()):
            raise ValidationError("Brand id or name is required")
        brand_id = _slugify(name)
        data["id"] = brand_id

    if "avatar_path" in data and data["avatar_path"] is not None:
        data["avatar_path"] = validate_safe_asset_path(data["avatar_path"])
    if "logo_path" in data and data["logo_path"] is not None:
        data["logo_path"] = validate_safe_asset_path(data["logo_path"])

    with _STORE_LOCK:
        brands = _load_brands_locked()
        now = _utcnow_iso()
        if brand_id in brands:
            data.setdefault("created_at", brands[brand_id].get("created_at", now))
        else:
            data.setdefault("created_at", now)
        data["updated_at"] = now
        data.pop("_is_seed", None)

        brands[brand_id] = data
        _atomic_write_json(get_brands_path(), brands)
        return dict(data)



def delete_brand(brand_id: str) -> bool:
    if not brand_id:
        raise ValidationError("Brand id is required")
    with _STORE_LOCK:
        brands = _load_brands_locked()
        if brand_id not in brands:
            raise NotFoundError(f"Brand not found: {brand_id}")
        del brands[brand_id]
        _atomic_write_json(get_brands_path(), brands)
        return True


# ---------------------------------------------------------------------------
# Template Storage Operations
# ---------------------------------------------------------------------------

def _load_templates_locked() -> Dict[str, Dict[str, Any]]:
    path = get_templates_path()
    templates = _read_json_file(path)
    if not templates:
        templates = {DEFAULT_TEMPLATE_ID: dict(DEFAULT_TEMPLATE_DICT)}
        _atomic_write_json(path, templates)
    return templates


def list_templates() -> List[Dict[str, Any]]:
    with _STORE_LOCK:
        templates = _load_templates_locked()
        return sorted(templates.values(), key=lambda t: (t.get("name") or t.get("id", "")).lower())


def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    if not template_id:
        return None
    with _STORE_LOCK:
        templates = _load_templates_locked()
        template = templates.get(template_id)
        return dict(template) if template else None


def get_template_or_raise(template_id: str) -> Dict[str, Any]:
    template = get_template(template_id)
    if template is None:
        raise NotFoundError(f"Template not found: {template_id}")
    return template


def create_template(template: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    data = _to_dict(template)
    tid = data.get("id") or data.get("template_id")
    if not tid or (isinstance(tid, str) and not tid.strip()):
        name = data.get("name")
        if not name or (isinstance(name, str) and not name.strip()):
            raise ValidationError("Template id or name is required")
        tid = _slugify(name)
        data["id"] = tid
    else:
        data["id"] = tid

    with _STORE_LOCK:
        templates = _load_templates_locked()
        if tid in templates:
            raise ConflictError(f"Template already exists: {tid}")

        now = _utcnow_iso()
        data.setdefault("created_at", now)
        data["updated_at"] = now

        templates[tid] = data
        _atomic_write_json(get_templates_path(), templates)
        return dict(data)


def update_template(template_id: str, updates: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    if not template_id:
        raise ValidationError("Template id is required")
    patch = _to_dict(updates)

    with _STORE_LOCK:
        templates = _load_templates_locked()
        if template_id not in templates:
            raise NotFoundError(f"Template not found: {template_id}")

        existing = templates[template_id]
        for k, v in patch.items():
            if k in ("id", "template_id", "created_at"):
                continue
            if v is not None:
                existing[k] = v

        existing["updated_at"] = _utcnow_iso()
        templates[template_id] = existing
        _atomic_write_json(get_templates_path(), templates)
        return dict(existing)


def save_template(template: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    data = _to_dict(template)
    tid = data.get("id") or data.get("template_id")
    if not tid or (isinstance(tid, str) and not tid.strip()):
        name = data.get("name")
        if not name or (isinstance(name, str) and not name.strip()):
            raise ValidationError("Template id or name is required")
        tid = _slugify(name)
        data["id"] = tid
    else:
        data["id"] = tid

    with _STORE_LOCK:
        templates = _load_templates_locked()
        now = _utcnow_iso()
        if tid in templates:
            data.setdefault("created_at", templates[tid].get("created_at", now))
        else:
            data.setdefault("created_at", now)
        data["updated_at"] = now

        templates[tid] = data
        _atomic_write_json(get_templates_path(), templates)
        return dict(data)



def delete_template(template_id: str) -> bool:
    if not template_id:
        raise ValidationError("Template id is required")
    with _STORE_LOCK:
        templates = _load_templates_locked()
        if template_id not in templates:
            raise NotFoundError(f"Template not found: {template_id}")
        del templates[template_id]
        _atomic_write_json(get_templates_path(), templates)
        return True


# ---------------------------------------------------------------------------
# Batch and Item Storage Operations
# ---------------------------------------------------------------------------

def _load_batches_locked() -> Dict[str, Dict[str, Any]]:
    path = get_batches_path()
    return _read_json_file(path)


def list_batches() -> List[Dict[str, Any]]:
    with _STORE_LOCK:
        batches = _load_batches_locked()
        return sorted(batches.values(), key=lambda b: b.get("created_at", ""), reverse=True)


def get_batch(batch_id: str) -> Optional[Dict[str, Any]]:
    if not batch_id:
        return None
    with _STORE_LOCK:
        batches = _load_batches_locked()
        batch = batches.get(batch_id)
        return dict(batch) if batch else None


def get_batch_or_raise(batch_id: str) -> Dict[str, Any]:
    batch = get_batch(batch_id)
    if batch is None:
        raise NotFoundError(f"Batch not found: {batch_id}")
    return batch


def create_batch(batch: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    data = _to_dict(batch)
    brand_id = data.get("brand_id")
    if not brand_id or not str(brand_id).strip():
        raise ValidationError("brand_id is required")

    raw_items = data.get("items")
    if not raw_items or not isinstance(raw_items, list) or len(raw_items) == 0:
        raise ValidationError("Batch must contain at least one item")

    with _STORE_LOCK:
        brands = _load_brands_locked()
        if brand_id not in brands:
            raise NotFoundError(f"Brand not found: {brand_id}")

        batch_id = data.get("batch_id") or data.get("id")
        if not batch_id or not str(batch_id).strip():
            batch_id = str(uuid.uuid4())
        else:
            clean_batch_id = str(batch_id).strip()
            if not SAFE_ID_RE.match(clean_batch_id):
                raise ValidationError(f"Invalid batch_id: {clean_batch_id!r}")
            batch_id = clean_batch_id

        data["batch_id"] = batch_id
        data["id"] = batch_id

        batches = _load_batches_locked()
        if batch_id in batches:
            raise ConflictError(f"Batch already exists: {batch_id}")

        brand = brands[brand_id]
        template_id = data.get("template_id") or brand.get("template_id") or DEFAULT_TEMPLATE_ID
        templates = _load_templates_locked()
        if template_id not in templates:
            raise NotFoundError(f"Template not found: {template_id}")
        data["template_id"] = template_id

        now = _utcnow_iso()
        data.setdefault("created_at", now)
        data["updated_at"] = now
        data["status"] = data.get("status") or "PENDING"

        seen_item_ids = set()
        processed_items = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict) and not hasattr(raw_item, "__dict__"):
                raise ValidationError("Each item in items must be an object/dictionary")
            item = _to_dict(raw_item)
            if not item.get("source_url") or not str(item.get("source_url")).strip():
                raise ValidationError("Each item must have a non-empty source_url")
            item_id = item.get("id") or item.get("item_id")
            if not item_id or not str(item_id).strip() or str(item_id).strip() in seen_item_ids:
                item_id = str(uuid.uuid4())
            else:
                clean_item_id = str(item_id).strip()
                if not SAFE_ID_RE.match(clean_item_id):
                    raise ValidationError(f"Invalid item_id: {clean_item_id!r}")
                item_id = clean_item_id
            seen_item_ids.add(item_id)
            item["id"] = item_id
            item["item_id"] = item_id
            item["batch_id"] = batch_id
            item["brand_id"] = brand_id
            item.setdefault("status", "PENDING")
            item.setdefault("source_path", None)
            item.setdefault("rendered_path", None)
            item.setdefault("error_message", None)
            item.setdefault("created_at", now)
            item.setdefault("updated_at", now)
            processed_items.append(item)

        data["items"] = processed_items
        data["total_items"] = len(processed_items)

        batches[batch_id] = data
        _atomic_write_json(get_batches_path(), batches)
        return dict(data)


def update_batch(batch_id: str, updates: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    if not batch_id:
        raise ValidationError("batch_id is required")
    patch = _to_dict(updates)

    with _STORE_LOCK:
        batches = _load_batches_locked()
        if batch_id not in batches:
            raise NotFoundError(f"Batch not found: {batch_id}")

        existing = batches[batch_id]
        for k, v in patch.items():
            if k in ("batch_id", "id", "created_at"):
                continue
            if v is not None:
                existing[k] = v

        existing["updated_at"] = _utcnow_iso()
        batches[batch_id] = existing
        _atomic_write_json(get_batches_path(), batches)
        return dict(existing)


def save_batch(batch: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    data = _to_dict(batch)
    batch_id = data.get("batch_id") or data.get("id")
    if not batch_id:
        raise ValidationError("batch_id is required")
    data["batch_id"] = batch_id
    if "id" not in data:
        data["id"] = batch_id

    with _STORE_LOCK:
        batches = _load_batches_locked()
        now = _utcnow_iso()
        if batch_id in batches:
            data.setdefault("created_at", batches[batch_id].get("created_at", now))
        else:
            data.setdefault("created_at", now)
        data["updated_at"] = now
        data.setdefault("items", [])

        batches[batch_id] = data
        _atomic_write_json(get_batches_path(), batches)
        return dict(data)


def get_item(item_id: str) -> Optional[Dict[str, Any]]:
    if not item_id:
        return None
    with _STORE_LOCK:
        batches = _load_batches_locked()
        for batch in batches.values():
            for item in batch.get("items", []):
                if item.get("id") == item_id or item.get("item_id") == item_id:
                    res = dict(item)
                    res["batch_id"] = batch.get("batch_id") or batch.get("id")
                    return res
        return None


def get_item_or_raise(item_id: str) -> Dict[str, Any]:
    item = get_item(item_id)
    if item is None:
        raise NotFoundError(f"Item not found: {item_id}")
    return item


def update_item(item_id: str, updates: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    if not item_id:
        raise ValidationError("item_id is required")
    patch = _to_dict(updates)

    with _STORE_LOCK:
        batches = _load_batches_locked()
        found_item = None

        for batch in batches.values():
            for idx, item in enumerate(batch.get("items", [])):
                if item.get("id") == item_id or item.get("item_id") == item_id:
                    for k, v in patch.items():
                        if k in ("id", "item_id", "batch_id", "created_at"):
                            continue
                        if v is not None or k in (
                            "error_message",
                            "source_path",
                            "rendered_path",
                            "manual_headline",
                            "additional_instructions",
                            "selected_headline",
                            "caption",
                            "product_url",
                            "product_code",
                            "ai_copy",
                            "job_id",
                            "publication_records",
                        ):
                            item[k] = v
                    item["updated_at"] = _utcnow_iso()
                    batch["items"][idx] = item
                    batch["updated_at"] = _utcnow_iso()
                    found_item = dict(item)
                    found_item["batch_id"] = batch.get("batch_id") or batch.get("id")
                    break
            if found_item:
                break

        if not found_item:
            raise NotFoundError(f"Item not found: {item_id}")

        _atomic_write_json(get_batches_path(), batches)
        return found_item


def reserve_publication(item_id: str, key: str, requested_at: str) -> Dict[str, Any]:
    """Atomically return or reserve an idempotent publication record."""
    with _STORE_LOCK:
        batches = _load_batches_locked()
        for batch in batches.values():
            for index, item in enumerate(batch.get("items", [])):
                if item.get("id") != item_id and item.get("item_id") != item_id:
                    continue
                records = list(item.get("publication_records") or [])
                existing = next((record for record in records if record.get("key") == key), None)
                if existing:
                    return {"reserved": False, "record": dict(existing)}
                record = {"key": key, "status": "dispatching", "requested_at": requested_at}
                records.append(record)
                item["publication_records"] = records
                item["updated_at"] = _utcnow_iso()
                batch["items"][index] = item
                _atomic_write_json(get_batches_path(), batches)
                return {"reserved": True, "record": dict(record)}
        raise NotFoundError(f"Item not found: {item_id}")


def finish_publication(item_id: str, key: str, record: Dict[str, Any], *, status: Optional[str] = None) -> Dict[str, Any]:
    """Atomically replace a reserved publication record and optional item state."""
    with _STORE_LOCK:
        batches = _load_batches_locked()
        for batch in batches.values():
            for index, item in enumerate(batch.get("items", [])):
                if item.get("id") != item_id and item.get("item_id") != item_id:
                    continue
                records = list(item.get("publication_records") or [])
                for record_index, existing in enumerate(records):
                    if existing.get("key") == key:
                        records[record_index] = dict(record)
                        break
                else:
                    raise ValidationError("Publication reservation not found")
                item["publication_records"] = records
                if status:
                    item["status"] = status
                item["updated_at"] = _utcnow_iso()
                batch["items"][index] = item
                _atomic_write_json(get_batches_path(), batches)
                return dict(item)
        raise NotFoundError(f"Item not found: {item_id}")


def save_item(item: Union[Dict[str, Any], Any]) -> Dict[str, Any]:
    data = _to_dict(item)
    item_id = data.get("id") or data.get("item_id")
    if not item_id:
        raise ValidationError("item_id is required")
    return update_item(item_id, data)


def seed_defaults(force: bool = False) -> None:
    """Explicitly seed default brand and template if missing or forced."""
    with _STORE_LOCK:
        brands_path = get_brands_path()
        templates_path = get_templates_path()

        if force or not os.path.exists(brands_path) or not _read_json_file(brands_path):
            _atomic_write_json(brands_path, {DEFAULT_BRAND_ID: dict(DEFAULT_BRAND_DICT)})

        if force or not os.path.exists(templates_path) or not _read_json_file(templates_path):
            _atomic_write_json(templates_path, {DEFAULT_TEMPLATE_ID: dict(DEFAULT_TEMPLATE_DICT)})


def reset_store() -> None:
    """Clear all stored files (primarily for test teardown)."""
    with _STORE_LOCK:
        for path in (get_brands_path(), get_templates_path(), get_batches_path()):
            if path and os.path.exists(path):
                with contextlib.suppress(OSError):
                    os.remove(path)
