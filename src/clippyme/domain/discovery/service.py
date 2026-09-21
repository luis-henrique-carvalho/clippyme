from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import tempfile
import threading
from typing import Dict, List, Optional

from .base import DiscoveryProvider
from .providers.instagram_provider import InstagramProvider
from .providers.tiktok_provider import TikTokProvider
from .providers.youtube_provider import YouTubeProvider
from .schemas import DiscoveryFilter, DiscoveryItem, DiscoveryResult, PlatformType, SortOrder

logger = logging.getLogger("clippyme.discovery.service")

CACHE_DIR = os.path.join("data", "cache", "discovery")
CACHE_TTL_SECONDS = 3600  # 1 hora de cache para buscas idênticas
_SERVICE_LOCK = threading.RLock()


class DiscoveryService:
    """Serviço central de descoberta e ranqueamento de vídeos virais."""

    def __init__(self):
        self._providers: Dict[PlatformType, DiscoveryProvider] = {
            PlatformType.INSTAGRAM: InstagramProvider(),
            PlatformType.TIKTOK: TikTokProvider(),
            PlatformType.YOUTUBE: YouTubeProvider(),
        }

    def _get_cache_key(self, filter_params: DiscoveryFilter) -> str:
        key_raw = f"{filter_params.platform}:{filter_params.query.lower().strip()}:{filter_params.limit}"
        return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()

    def _read_cache(self, cache_key: str) -> Optional[DiscoveryResult]:
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        if not os.path.exists(cache_file):
            return None
        try:
            mtime = os.path.getmtime(cache_file)
            if datetime.datetime.now().timestamp() - mtime > CACHE_TTL_SECONDS:
                return None
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["cached"] = True
                return DiscoveryResult(**data)
        except Exception as exc:
            logger.debug("Cache miss ou erro de leitura: %s", exc)
            return None

    def _write_cache(self, cache_key: str, result: DiscoveryResult) -> None:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
            data = result.model_dump(mode="json")
            
            # Atomic write
            fd, tmp_path = tempfile.mkstemp(prefix=".disc-", suffix=".tmp", dir=CACHE_DIR)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, cache_file)
        except Exception as exc:
            logger.warning("Falha ao salvar cache de descoberta: %s", exc)

    def _sort_items(self, items: List[DiscoveryItem], sort_by: SortOrder) -> List[DiscoveryItem]:
        if sort_by == SortOrder.VIRALITY_SCORE:
            return sorted(items, key=lambda x: (x.virality_score, x.view_count), reverse=True)
        elif sort_by == SortOrder.VIEW_COUNT:
            return sorted(items, key=lambda x: x.view_count, reverse=True)
        elif sort_by == SortOrder.RECENT:
            return sorted(items, key=lambda x: x.published_timestamp or 0, reverse=True)
        elif sort_by == SortOrder.ENGAGEMENT_RATE:
            return sorted(items, key=lambda x: (x.engagement_rate, x.virality_score), reverse=True)
        return items

    async def search(self, filter_params: DiscoveryFilter) -> DiscoveryResult:
        """Executa a busca com cache, roteamento para o provedor e ordenação."""
        cache_key = self._get_cache_key(filter_params)
        cached_result = self._read_cache(cache_key)
        if cached_result:
            # Re-aplica ordenação e filtros caso o usuário altere sort_by
            sorted_items = self._sort_items(cached_result.items, filter_params.sort_by)
            if filter_params.max_age_days:
                min_timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp() - (filter_params.max_age_days * 86400)
                sorted_items = [item for item in sorted_items if item.published_timestamp is None or item.published_timestamp >= min_timestamp]
            if filter_params.min_views:
                sorted_items = [item for item in sorted_items if item.view_count >= filter_params.min_views]
            cached_result.items = sorted_items
            return cached_result

        provider = self._providers.get(filter_params.platform)
        if not provider:
            from clippyme.domain.errors import ValidationError
            raise ValidationError(f"Provedor não suportado para plataforma: {filter_params.platform}")

        items = await provider.search(filter_params)

        # Filtro de max_age_days (apenas descarta se o timestamp for conhecido e antigo)
        if filter_params.max_age_days:
            min_timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp() - (filter_params.max_age_days * 86400)
            items = [item for item in items if item.published_timestamp is None or item.published_timestamp >= min_timestamp]

        # Filtro de views mínimas
        if filter_params.min_views:
            items = [item for item in items if item.view_count >= filter_params.min_views]

        sorted_items = self._sort_items(items, filter_params.sort_by)

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result = DiscoveryResult(
            query=filter_params.query,
            platform=filter_params.platform,
            total_found=len(sorted_items),
            items=sorted_items,
            cached=False,
            fetched_at=now_iso,
        )

        if result.items:
            self._write_cache(cache_key, result)

        return result


_discovery_service_instance: Optional[DiscoveryService] = None


def get_discovery_service() -> DiscoveryService:
    global _discovery_service_instance
    with _SERVICE_LOCK:
        if _discovery_service_instance is None:
            _discovery_service_instance = DiscoveryService()
        return _discovery_service_instance
