"""FastAPI route handlers for Viral Content Studio (Milestone 1).

Covers Brand and Template management endpoints under /api/viral-studio.
Handlers adhere to the thin-handler rule (<25 lines), delegating all I/O to
clippyme.domain.viral_studio_store and validation to viral_studio_schemas.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response, status

from clippyme.api.viral_studio_schemas import (
    BatchCreateRequest,
    BatchListResponse,
    BatchResponse,
    BrandCreate,
    BrandListResponse,
    BrandResponse,
    BrandUpdate,
    TemplateCreate,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdate,
    ViralItem,
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


# ---------------------------------------------------------------------------
# Batch & Item Endpoints
# ---------------------------------------------------------------------------

@router.get("/batches", response_model=BatchListResponse)
async def list_batches():
    """List all batches."""
    batches = await asyncio.to_thread(viral_studio_store.list_batches)
    return BatchListResponse(batches=batches, total=len(batches))


@router.get("/batches/{id}", response_model=BatchResponse)
async def get_batch(id: str):
    """Retrieve a single batch with all item statuses."""
    batch = await asyncio.to_thread(viral_studio_store.get_batch_or_raise, id)
    return batch


@router.post(
    "/batches",
    response_model=BatchResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        202: {"model": BatchResponse, "description": "Batch accepted for background processing"},
    },
)
async def create_batch(
    payload: BatchCreateRequest,
    request: Request,
    response: Response,
):
    """Create and persist a new batch of items, enqueuing them in PENDING state."""
    batch = await asyncio.to_thread(viral_studio_store.create_batch, payload)
    is_async = (
        request.headers.get("Prefer") == "respond-async"
        or request.query_params.get("async") == "true"
        or (request.headers.get("X-Gemini-Key") and request.query_params.get("async") != "false")
    )
    if is_async:
        response.status_code = status.HTTP_202_ACCEPTED
    else:
        response.status_code = status.HTTP_201_CREATED
    return batch


@router.get("/items/{id}", response_model=ViralItem)
async def get_item(id: str):
    """Retrieve details and processing status of a single viral item."""
    item = await asyncio.to_thread(viral_studio_store.get_item_or_raise, id)
    return item

