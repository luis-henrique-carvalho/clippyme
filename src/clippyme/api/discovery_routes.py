"""FastAPI route handlers for multi-platform video discovery."""
from __future__ import annotations

import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status

from clippyme.domain.discovery import (
    DiscoveryFilter,
    DiscoveryResult,
    PlatformType,
    get_discovery_service,
)

logger = logging.getLogger("clippyme.api.discovery")
router = APIRouter(prefix="/api/discover", tags=["discovery"])


@router.get("/platforms")
async def get_available_platforms() -> Dict[str, Any]:
    """Retorna a lista de plataformas suportadas para busca de vídeos virais."""
    return {
        "platforms": [
            {
                "id": PlatformType.INSTAGRAM.value,
                "name": "Instagram Reels",
                "icon": "instagram",
                "description": "Busca por hashtag, explorador e Reels virais",
                "enabled": True,
            },
            {
                "id": PlatformType.TIKTOK.value,
                "name": "TikTok",
                "icon": "video",
                "description": "Busca por hashtags e tendências",
                "enabled": True,
            },
            {
                "id": PlatformType.YOUTUBE.value,
                "name": "YouTube Shorts",
                "icon": "youtube",
                "description": "Busca por palavras-chave com ordenação por visualizações",
                "enabled": True,
            },
        ]
    }


@router.post("/search", response_model=DiscoveryResult)
async def search_viral_videos(filter_params: DiscoveryFilter) -> DiscoveryResult:
    """
    Pesquisa vídeos virais por palavra-chave/hashtag em uma plataforma suportada,
    calcula as métricas de engajamento e ranqueia os resultados.
    """
    service = get_discovery_service()
    result = await service.search(filter_params)
    return result
