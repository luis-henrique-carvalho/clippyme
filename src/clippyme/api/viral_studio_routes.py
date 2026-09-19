"""FastAPI route handlers for Viral Content Studio (Milestone 1).

Covers Brand and Template management endpoints under /api/viral-studio.
Handlers adhere to the thin-handler rule (<25 lines), delegating all I/O to
clippyme.domain.viral_studio_store and validation to viral_studio_schemas.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, status

from clippyme.api.viral_studio_schemas import (
    BrandCreate,
    BrandListResponse,
    BrandResponse,
    BrandUpdate,
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
)
from clippyme.domain import viral_studio_store

router = APIRouter(tags=["viral-studio"])


# ---------------------------------------------------------------------------
# Brand Endpoints
# ---------------------------------------------------------------------------

@router.get("/brands", response_model=BrandListResponse)
async def list_brands():
    """List all configured brand profiles."""
    brands = await asyncio.to_thread(viral_studio_store.list_brands)
    return BrandListResponse(brands=brands, total=len(brands))


@router.get("/brands/{id}", response_model=BrandResponse)
async def get_brand(id: str):
    """Retrieve a single brand profile by ID."""
    brand = await asyncio.to_thread(viral_studio_store.get_brand_or_raise, id)
    return brand


@router.post("/brands", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(payload: BrandCreate):
    """Create and persist a new brand profile."""
    brand = await asyncio.to_thread(viral_studio_store.create_brand, payload)
    return brand


@router.patch("/brands/{id}", response_model=BrandResponse)
async def update_brand(id: str, payload: BrandUpdate):
    """Partially update an existing brand profile."""
    brand = await asyncio.to_thread(viral_studio_store.update_brand, id, payload)
    return brand


# ---------------------------------------------------------------------------
# Template Endpoints
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=TemplateListResponse)
async def list_templates():
    """List all visual composition templates."""
    templates = await asyncio.to_thread(viral_studio_store.list_templates)
    return TemplateListResponse(templates=templates, total=len(templates))


@router.get("/templates/{id}", response_model=TemplateResponse)
async def get_template(id: str):
    """Retrieve a single visual template by ID."""
    template = await asyncio.to_thread(viral_studio_store.get_template_or_raise, id)
    return template


@router.post("/templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(payload: TemplateCreate):
    """Create and persist a new visual template."""
    template = await asyncio.to_thread(viral_studio_store.create_template, payload)
    return template


@router.patch("/templates/{id}", response_model=TemplateResponse)
async def update_template(id: str, payload: TemplateUpdate):
    """Partially update an existing visual template."""
    template = await asyncio.to_thread(viral_studio_store.update_template, id, payload)
    return template

