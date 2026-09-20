"""Pydantic request and response schemas for Viral Content Studio.

Covers Brand and VisualTemplate models, request validation, and default seed records.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from clippyme.api.schemas import _reject_internal_host
from clippyme.domain.errors import ValidationError as DomainValidationError
from clippyme.domain.viral_studio_store import (
    validate_safe_asset_path as _store_validate_asset_path,
)
from clippyme.domain.viral_studio_download import validate_viral_source_url

HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
HANDLE_CHARS_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def slugify(text: str) -> str:
    """Convert arbitrary text to a URL/identifier-safe slug."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", text).strip("-_") or "unnamed"


def validate_affiliate_url(v: Optional[str]) -> Optional[str]:
    """Validate that affiliate URL is a public HTTP/HTTPS URL."""
    if v is None:
        return None
    raw = v.strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError("URL must use http or https")
    if not parsed.hostname:
        raise ValueError("URL has no host")
    _reject_internal_host(parsed.hostname.lower())
    return raw


def validate_safe_asset_path(v: Optional[str]) -> Optional[str]:
    """Validate that asset path does not contain path traversal characters or absolute paths."""
    try:
        return _store_validate_asset_path(v)
    except DomainValidationError as exc:
        raise ValueError(exc.detail) from exc


def _validate_hex(v: str, field_name: str = "Color") -> str:
    if not isinstance(v, str):
        raise ValueError(f"{field_name} must be a string")
    clean = v.strip().upper()
    if not HEX_COLOR_RE.match(clean):
        raise ValueError(f"Invalid hex color {v!r}. Must match #RGB, #RRGGBB, or #RRGGBBAA")
    return clean


# ============================================================================
# Brand Schemas
# ============================================================================

class BrandBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    handle: str = Field(..., min_length=1, max_length=60)
    avatar_path: Optional[str] = Field(None, max_length=512)
    logo_path: Optional[str] = Field(None, max_length=512)
    default_cta: str = Field("Confira os achadinhos no link da bio!", max_length=500)
    default_affiliate_url: Optional[str] = Field(None, max_length=2048)
    template_id: str = Field("classic-affiliate", max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    publishing_profiles: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Brand name must not be blank")
        return v

    @field_validator("handle")
    @classmethod
    def _clean_handle(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Handle must not be blank")
        clean = v.lstrip("@")
        if not clean:
            raise ValueError("Handle must contain characters after '@'")
        if not HANDLE_CHARS_RE.match(clean):
            raise ValueError("Handle contains invalid characters (allowed: letters, numbers, dot, underscore, dash)")
        return f"@{clean}"

    @field_validator("default_affiliate_url")
    @classmethod
    def _check_affiliate_url(cls, v: Optional[str]) -> Optional[str]:
        return validate_affiliate_url(v)

    @field_validator("avatar_path", "logo_path")
    @classmethod
    def _check_asset_path(cls, v: Optional[str]) -> Optional[str]:
        return validate_safe_asset_path(v)

    @field_validator("publishing_profiles")
    @classmethod
    def _check_publishing_profiles(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("publishing_profiles must be an object/dict")
        if len(v) > 16:
            raise ValueError("Too many publishing profiles (maximum 16)")
        for key in v:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("publishing_profiles keys must be non-empty strings")
        return v


class Brand(BrandBase):
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BrandCreate(BaseModel):
    id: Optional[str] = Field(None, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=100)
    handle: str = Field(..., min_length=1, max_length=60)
    avatar_path: Optional[str] = Field(None, max_length=512)
    logo_path: Optional[str] = Field(None, max_length=512)
    default_cta: str = Field("Confira os achadinhos no link da bio!", max_length=500)
    default_affiliate_url: Optional[str] = Field(None, max_length=2048)
    template_id: str = Field("classic-affiliate", max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    publishing_profiles: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _auto_generate_id(cls, values: Any) -> Any:
        if isinstance(values, dict):
            raw_id = values.get("id")
            if not raw_id or (isinstance(raw_id, str) and not raw_id.strip()):
                name = values.get("name")
                if isinstance(name, str) and name.strip():
                    values["id"] = slugify(name)[:64].rstrip("-_") or "unnamed"
        return values

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Brand name must not be blank")
        return v

    @field_validator("handle")
    @classmethod
    def _clean_handle(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Handle must not be blank")
        clean = v.lstrip("@")
        if not clean:
            raise ValueError("Handle must contain characters after '@'")
        if not HANDLE_CHARS_RE.match(clean):
            raise ValueError("Handle contains invalid characters (allowed: letters, numbers, dot, underscore, dash)")
        return f"@{clean}"

    @field_validator("default_affiliate_url")
    @classmethod
    def _check_affiliate_url(cls, v: Optional[str]) -> Optional[str]:
        return validate_affiliate_url(v)

    @field_validator("avatar_path", "logo_path")
    @classmethod
    def _check_asset_path(cls, v: Optional[str]) -> Optional[str]:
        return validate_safe_asset_path(v)

    @field_validator("publishing_profiles")
    @classmethod
    def _check_publishing_profiles(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("publishing_profiles must be an object/dict")
        if len(v) > 16:
            raise ValueError("Too many publishing profiles (maximum 16)")
        for key in v:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("publishing_profiles keys must be non-empty strings")
        return v


class BrandUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    handle: Optional[str] = Field(None, min_length=1, max_length=60)
    avatar_path: Optional[str] = Field(None, max_length=512)
    logo_path: Optional[str] = Field(None, max_length=512)
    default_cta: Optional[str] = Field(None, max_length=500)
    default_affiliate_url: Optional[str] = Field(None, max_length=2048)
    template_id: Optional[str] = Field(None, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    publishing_profiles: Optional[Dict[str, Any]] = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Brand name must not be blank")
        return v

    @field_validator("handle")
    @classmethod
    def _clean_handle(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Handle must not be blank")
        clean = v.lstrip("@")
        if not clean:
            raise ValueError("Handle must contain characters after '@'")
        if not HANDLE_CHARS_RE.match(clean):
            raise ValueError("Handle contains invalid characters (allowed: letters, numbers, dot, underscore, dash)")
        return f"@{clean}"

    @field_validator("default_affiliate_url")
    @classmethod
    def _check_affiliate_url(cls, v: Optional[str]) -> Optional[str]:
        return validate_affiliate_url(v)

    @field_validator("avatar_path", "logo_path")
    @classmethod
    def _check_asset_path(cls, v: Optional[str]) -> Optional[str]:
        return validate_safe_asset_path(v)

    @field_validator("publishing_profiles")
    @classmethod
    def _check_publishing_profiles(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("publishing_profiles must be an object/dict")
        if len(v) > 16:
            raise ValueError("Too many publishing profiles (maximum 16)")
        for key in v:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("publishing_profiles keys must be non-empty strings")
        return v


class BrandResponse(Brand):
    """Response model for a single brand (matches Brand schema directly)."""
    pass


class BrandListResponse(BaseModel):
    """Response model for listing brands."""
    brands: List[Brand] = Field(default_factory=list)
    total: int = 0

    @model_validator(mode="before")
    @classmethod
    def _set_total(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "total" not in values and "brands" in values and isinstance(values["brands"], list):
                values["total"] = len(values["brands"])
        return values


# ============================================================================
# VisualTemplate Schemas
# ============================================================================

class VisualTemplate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field("classic-affiliate", max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field("Classic Affiliate", min_length=1, max_length=100)
    width: int = Field(1080, ge=360, le=3840)
    height: int = Field(1920, ge=640, le=3840)
    background_color: str = Field("#FFFFFF", max_length=9)
    avatar_enabled: bool = True
    brand_name_enabled: bool = True
    headline_enabled: bool = True
    watermark_enabled: bool = True
    video_fit: str = Field("contain", pattern=r"^(contain|cover|crop)$")

    # Geometry & Typography settings
    avatar_x: int = Field(60, ge=0, le=3840)
    avatar_y: int = Field(80, ge=0, le=3840)
    avatar_size: int = Field(100, ge=20, le=1000)
    brand_name_font_size: int = Field(36, ge=10, le=200)
    brand_name_color: str = Field("#111111", max_length=9)
    handle_font_size: int = Field(26, ge=10, le=160)
    handle_color: str = Field("#666666", max_length=9)
    headline_font_size: int = Field(48, ge=12, le=200)
    headline_color: str = Field("#111111", max_length=9)
    headline_max_lines: int = Field(3, ge=1, le=8)
    headline_margin_x: int = Field(60, ge=0, le=1000)
    headline_margin_top: int = Field(30, ge=0, le=1000)
    watermark_opacity: float = Field(0.7, ge=0.0, le=1.0)
    watermark_position: str = Field("bottom-right", pattern=r"^(top-left|top-right|bottom-left|bottom-right|center)$")

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="before")
    @classmethod
    def _sync_template_id(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "id" not in values and "template_id" in values:
                values["id"] = values["template_id"]
        return values

    @property
    def template_id(self) -> str:
        return self.id

    @field_validator("background_color", "brand_name_color", "handle_color", "headline_color")
    @classmethod
    def _check_hex_color(cls, v: str) -> str:
        return _validate_hex(v)


class TemplateCreate(BaseModel):
    id: Optional[str] = Field(None, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field("Classic Affiliate", min_length=1, max_length=100)
    width: int = Field(1080, ge=360, le=3840)
    height: int = Field(1920, ge=640, le=3840)
    background_color: str = Field("#FFFFFF", max_length=9)
    avatar_enabled: bool = True
    brand_name_enabled: bool = True
    headline_enabled: bool = True
    watermark_enabled: bool = True
    video_fit: str = Field("contain", pattern=r"^(contain|cover|crop)$")
    avatar_x: int = Field(60, ge=0, le=3840)
    avatar_y: int = Field(80, ge=0, le=3840)
    avatar_size: int = Field(100, ge=20, le=1000)
    brand_name_font_size: int = Field(36, ge=10, le=200)
    brand_name_color: str = Field("#111111", max_length=9)
    handle_font_size: int = Field(26, ge=10, le=160)
    handle_color: str = Field("#666666", max_length=9)
    headline_font_size: int = Field(48, ge=12, le=200)
    headline_color: str = Field("#111111", max_length=9)
    headline_max_lines: int = Field(3, ge=1, le=8)
    headline_margin_x: int = Field(60, ge=0, le=1000)
    headline_margin_top: int = Field(30, ge=0, le=1000)
    watermark_opacity: float = Field(0.7, ge=0.0, le=1.0)
    watermark_position: str = Field("bottom-right", pattern=r"^(top-left|top-right|bottom-left|bottom-right|center)$")

    @model_validator(mode="before")
    @classmethod
    def _sync_template_id(cls, values: Any) -> Any:
        if isinstance(values, dict):
            raw_id = values.get("id") or values.get("template_id")
            if not raw_id or (isinstance(raw_id, str) and not raw_id.strip()):
                name = values.get("name") or "Classic Affiliate"
                if isinstance(name, str) and name.strip():
                    values["id"] = slugify(name)[:64].rstrip("-_") or "unnamed"
            elif "id" not in values and "template_id" in values:
                values["id"] = values["template_id"]
        return values

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Template name must not be blank")
        return v

    @field_validator("background_color", "brand_name_color", "handle_color", "headline_color")
    @classmethod
    def _check_hex_color(cls, v: str) -> str:
        return _validate_hex(v)


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    width: Optional[int] = Field(None, ge=360, le=3840)
    height: Optional[int] = Field(None, ge=640, le=3840)
    background_color: Optional[str] = Field(None, max_length=9)
    avatar_enabled: Optional[bool] = None
    brand_name_enabled: Optional[bool] = None
    headline_enabled: Optional[bool] = None
    watermark_enabled: Optional[bool] = None
    video_fit: Optional[str] = Field(None, pattern=r"^(contain|cover|crop)$")
    avatar_x: Optional[int] = Field(None, ge=0, le=3840)
    avatar_y: Optional[int] = Field(None, ge=0, le=3840)
    avatar_size: Optional[int] = Field(None, ge=20, le=1000)
    brand_name_font_size: Optional[int] = Field(None, ge=10, le=200)
    brand_name_color: Optional[str] = Field(None, max_length=9)
    handle_font_size: Optional[int] = Field(None, ge=10, le=160)
    handle_color: Optional[str] = Field(None, max_length=9)
    headline_font_size: Optional[int] = Field(None, ge=12, le=200)
    headline_color: Optional[str] = Field(None, max_length=9)
    headline_max_lines: Optional[int] = Field(None, ge=1, le=8)
    headline_margin_x: Optional[int] = Field(None, ge=0, le=1000)
    headline_margin_top: Optional[int] = Field(None, ge=0, le=1000)
    watermark_opacity: Optional[float] = Field(None, ge=0.0, le=1.0)
    watermark_position: Optional[str] = Field(None, pattern=r"^(top-left|top-right|bottom-left|bottom-right|center)$")

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Template name must not be blank")
        return v

    @field_validator("background_color", "brand_name_color", "handle_color", "headline_color")
    @classmethod
    def _check_hex_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _validate_hex(v)


class TemplateResponse(VisualTemplate):
    pass


class TemplateListResponse(BaseModel):
    templates: List[VisualTemplate] = Field(default_factory=list)
    total: int = 0

    @model_validator(mode="before")
    @classmethod
    def _set_total(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "total" not in values and "templates" in values and isinstance(values["templates"], list):
                values["total"] = len(values["templates"])
        return values


# ============================================================================
# Forward-Compatibility Schemas (Milestones 2–5)
# ============================================================================

class ViralItemStatus(str, Enum):
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    ANALYZING = "ANALYZING"
    RENDERING = "RENDERING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AICopyData(BaseModel):
    product: str = Field(..., min_length=1, max_length=200)
    product_description: str = Field("", max_length=1000)
    headlines: List[str] = Field(..., min_length=1, max_length=10)
    selected_headline: str = Field(..., min_length=1, max_length=300)
    caption: str = Field(..., max_length=2200)
    hashtags: List[str] = Field(default_factory=list)


class ViralItemInput(BaseModel):
    source_url: str = Field(..., max_length=2048)
    product_code: Optional[str] = Field(None, max_length=64)
    product_url: Optional[str] = Field(None, max_length=2048)
    manual_headline: Optional[str] = Field(None, max_length=300)
    additional_instructions: Optional[str] = Field(None, max_length=1000)

    @field_validator("source_url")
    @classmethod
    def _check_source_url(cls, v: str) -> str:
        try:
            return validate_viral_source_url(v)
        except DomainValidationError as exc:
            raise ValueError(exc.detail) from exc

    @field_validator("product_url")
    @classmethod
    def _check_product_url(cls, v: Optional[str]) -> Optional[str]:
        return validate_affiliate_url(v)


class BatchCreateRequest(BaseModel):
    brand_id: str = Field(..., min_length=1, max_length=64)
    template_id: Optional[str] = Field(None, max_length=64)
    items: List[ViralItemInput] = Field(..., min_length=1, max_length=100)

    @field_validator("brand_id")
    @classmethod
    def _clean_brand_id(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("brand_id must not be blank")
        return v

    @field_validator("template_id")
    @classmethod
    def _clean_template_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ViralItem(BaseModel):
    id: str
    batch_id: Optional[str] = None
    brand_id: Optional[str] = None
    source_url: str
    product_code: Optional[str] = None
    product_url: Optional[str] = None
    manual_headline: Optional[str] = None
    additional_instructions: Optional[str] = None
    selected_headline: Optional[str] = None
    caption: Optional[str] = None
    ai_copy: Optional[AICopyData] = None
    status: ViralItemStatus = ViralItemStatus.PENDING
    source_path: Optional[str] = None
    rendered_path: Optional[str] = None
    error_message: Optional[str] = None
    job_id: Optional[str] = None
    source_metadata: Optional[Dict[str, Any]] = None
    ai_context_summary: Optional[Dict[str, Any]] = None
    ai_telemetry: Optional[Dict[str, Any]] = None
    keyframe_urls: List[str] = Field(default_factory=list)
    logs: List[Dict[str, Any]] = Field(default_factory=list)
    publication_records: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = ConfigDict(extra="ignore")


class BatchResponse(BaseModel):
    id: str
    batch_id: str
    brand_id: str
    template_id: Optional[str] = None
    status: str = "PENDING"
    total_items: int = 0
    items: List[ViralItem] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _sync_ids_and_totals(cls, values: Any) -> Any:
        if isinstance(values, dict):
            bid = values.get("batch_id") or values.get("id")
            if bid:
                values["id"] = bid
                values["batch_id"] = bid
            if "items" in values and isinstance(values["items"], list):
                values.setdefault("total_items", len(values["items"]))
        return values


class BatchListResponse(BaseModel):
    batches: List[BatchResponse] = Field(default_factory=list)
    total: int = 0

    @model_validator(mode="before")
    @classmethod
    def _set_total(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "total" not in values and "batches" in values and isinstance(values["batches"], list):
                values["total"] = len(values["batches"])
        return values


class ViralItemUpdate(BaseModel):
    selected_headline: Optional[str] = Field(None, max_length=300)
    caption: Optional[str] = Field(None, max_length=2200)
    product_code: Optional[str] = Field(None, max_length=64)
    product_url: Optional[str] = Field(None, max_length=2048)
    manual_headline: Optional[str] = Field(None, max_length=300)
    additional_instructions: Optional[str] = Field(None, max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("product_url")
    @classmethod
    def _check_product_url(cls, v: Optional[str]) -> Optional[str]:
        return validate_affiliate_url(v)


class ItemRenderRequest(BaseModel):
    headline: Optional[str] = Field(None, max_length=300)
    template_id: Optional[str] = Field(None, max_length=64)
    watermark: bool = True


class ViralPublishPlatform(BaseModel):
    platform: str = Field(..., max_length=64)
    accountId: Optional[str] = Field(None, max_length=128)
    account_id: Optional[str] = Field(None, max_length=128)
    platformSpecificData: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def _sync_account_id(cls, values: Any) -> Any:
        if isinstance(values, dict):
            acc = values.get("accountId") or values.get("account_id")
            if acc:
                values["accountId"] = acc
                values["account_id"] = acc
        return values


class ViralPublishRequest(BaseModel):
    item_ids: List[str] = Field(..., min_length=1, max_length=100)
    platforms: List[ViralPublishPlatform] = Field(..., min_length=1, max_length=16)
    schedule_mode: str = Field("now", pattern=r"^(now|auto|manual)$")
    scheduled_for: Optional[str] = Field(None, max_length=64)
    timezone: Optional[str] = Field(None, max_length=64)
    start_date: Optional[str] = Field(None, max_length=64)


class ViralPublishResult(BaseModel):
    item_id: str
    status: str
    post_id: Optional[str] = None
    platform_post_id: Optional[str] = None
    published_at: Optional[str] = None
    error: Optional[str] = None


class ViralPublishResponse(BaseModel):
    results: List[ViralPublishResult] = Field(default_factory=list)
    total: int = 0
    successful: int = 0
    failed: int = 0

    @model_validator(mode="before")
    @classmethod
    def _calculate_totals(cls, values: Any) -> Any:
        if isinstance(values, dict) and "results" in values and isinstance(values["results"], list):
            res_list = values["results"]
            values.setdefault("total", len(res_list))
            values.setdefault(
                "successful",
                sum(1 for r in res_list if (isinstance(r, dict) and r.get("status") in ("published", "scheduled")) or (hasattr(r, "status") and r.status in ("published", "scheduled"))),
            )
            values.setdefault(
                "failed",
                sum(1 for r in res_list if (isinstance(r, dict) and r.get("status") == "failed") or (hasattr(r, "status") and r.status == "failed")),
            )
        return values



# ============================================================================
# Seed Defaults
# ============================================================================

DEFAULT_TEMPLATE_ID = "classic-affiliate"
DEFAULT_BRAND_ID = "vale-o-clique"

DEFAULT_TEMPLATE = VisualTemplate(
    id=DEFAULT_TEMPLATE_ID,
    name="Classic Affiliate",
    width=1080,
    height=1920,
    background_color="#FFFFFF",
    avatar_enabled=True,
    brand_name_enabled=True,
    headline_enabled=True,
    watermark_enabled=True,
    video_fit="contain",
    avatar_x=60,
    avatar_y=80,
    avatar_size=100,
    brand_name_font_size=36,
    brand_name_color="#111111",
    handle_font_size=26,
    handle_color="#666666",
    headline_font_size=48,
    headline_color="#111111",
    headline_max_lines=3,
    headline_margin_x=60,
    headline_margin_top=30,
    watermark_opacity=0.7,
    watermark_position="bottom-right",
)

DEFAULT_BRAND = Brand(
    id=DEFAULT_BRAND_ID,
    name="Vale o Clique?",
    handle="@valeoclique",
    avatar_path=None,
    logo_path=None,
    default_cta="Confira os achadinhos no link da bio!",
    default_affiliate_url=None,
    template_id=DEFAULT_TEMPLATE_ID,
    publishing_profiles={},
)
