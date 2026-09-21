from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import List

from ..base import DiscoveryProvider
from ..schemas import DiscoveryFilter, DiscoveryItem, PlatformType
from ..scoring import calculate_virality_score, calculate_engagement_rate, calculate_view_velocity

logger = logging.getLogger("clippyme.discovery.youtube")


class YouTubeProvider(DiscoveryProvider):
    """Provedor de busca e descoberta de YouTube Shorts."""

    @property
    def platform(self) -> PlatformType:
        return PlatformType.YOUTUBE

    def _search_sync(self, query: str, limit: int = 20) -> List[DiscoveryItem]:
        items: List[DiscoveryItem] = []
        now = int(time.time())

        try:
            import urllib.parse
            import yt_dlp

            clean = query.strip()
            tag = clean[1:] if clean.startswith("#") else clean
            tag = tag.replace(" ", "")

            # 1. URLs de busca priorizando maior contagem de visualizações e páginas de hashtag
            encoded_query = urllib.parse.quote_plus(f"{clean} shorts" if "short" not in clean.lower() else clean)
            url_views = f"https://www.youtube.com/results?search_query={encoded_query}&sp=CAMSAhAB"
            url_hashtag = f"https://www.youtube.com/hashtag/{tag}"

            ydl_opts = {
                "extract_flat": True,
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
            }
            from clippyme.domain.cookie_resolver import resolve_platform_cookies
            cookies_path = resolve_platform_cookies("youtube")
            if cookies_path:
                ydl_opts["cookiefile"] = cookies_path

            candidates: List[dict] = []
            seen_ids = set()

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Estratégia 1: Página de hashtag no YouTube (se for termo único ou hashtag)
                if len(clean.split()) <= 2:
                    try:
                        info_tag = ydl.extract_info(url_hashtag, download=False)
                        for e in (info_tag.get("entries") or []):
                            if not e:
                                continue
                            vid = e.get("id")
                            if vid and vid not in seen_ids:
                                seen_ids.add(vid)
                                candidates.append(e)
                    except Exception as tag_err:
                        logger.debug("YouTube hashtag search fallback: %s", tag_err)

                # Estratégia 2: Busca no YouTube ordenada por visualizações (sp=CAMSAhAB)
                try:
                    info_views = ydl.extract_info(url_views, download=False)
                    for e in (info_views.get("entries") or []):
                        if not e:
                            continue
                        vid = e.get("id")
                        if vid and vid not in seen_ids:
                            seen_ids.add(vid)
                            candidates.append(e)
                except Exception as views_err:
                    logger.debug("YouTube sort by views search fallback: %s", views_err)

                # Estratégia 3: Se ainda tiver poucos candidatos, usa ytsearch ampliado
                if len(candidates) < 10:
                    try:
                        search_spec = f"ytsearch50:{clean} shorts"
                        info_spec = ydl.extract_info(search_spec, download=False)
                        for e in (info_spec.get("entries") or []):
                            if not e:
                                continue
                            vid = e.get("id")
                            if vid and vid not in seen_ids:
                                seen_ids.add(vid)
                                candidates.append(e)
                    except Exception as spec_err:
                        logger.debug("YouTube ytsearch fallback: %s", spec_err)

            # Processa e calcula viralidade dos candidatos
            processed_items: List[DiscoveryItem] = []
            for entry in candidates:
                video_id = entry.get("id")
                if not video_id:
                    continue

                duration = entry.get("duration")
                # Filtra vídeos longos (> 180s) para manter foco em Shorts / vídeos curtos
                if duration is not None and duration > 180:
                    continue

                title = entry.get("title") or "YouTube Short"
                uploader = entry.get("uploader") or entry.get("channel") or "YouTube Creator"
                uploader_id = entry.get("uploader_id") or uploader
                views = int(entry.get("view_count") or 0)
                likes = int(entry.get("like_count") or 0)
                comments = int(entry.get("comment_count") or 0)
                timestamp = entry.get("timestamp")

                thumbnail = entry.get("thumbnail")
                if not thumbnail and entry.get("thumbnails"):
                    thumbnail = entry["thumbnails"][-1].get("url")

                url = f"https://www.youtube.com/shorts/{video_id}"

                virality = calculate_virality_score(
                    platform=PlatformType.YOUTUBE,
                    views=views,
                    likes=likes,
                    comments=comments,
                    published_timestamp=timestamp,
                    current_timestamp=now,
                )

                item = DiscoveryItem(
                    id=video_id,
                    platform=PlatformType.YOUTUBE,
                    url=url,
                    title=title,
                    description=entry.get("description", "") or title,
                    author_name=uploader,
                    author_handle=f"@{uploader_id}" if not str(uploader_id).startswith("@") else str(uploader_id),
                    published_timestamp=timestamp,
                    duration_seconds=duration,
                    thumbnail_url=thumbnail,
                    view_count=views,
                    like_count=likes,
                    comment_count=comments,
                    virality_score=virality,
                    engagement_rate=calculate_engagement_rate(PlatformType.YOUTUBE, views, likes, comments),
                    view_velocity=calculate_view_velocity(views, timestamp, now),
                    raw_metadata={"duration": duration, "webpage_url": entry.get("webpage_url")},
                )
                processed_items.append(item)

            # Ordena inicialmente por virality_score e views decrescentes
            processed_items.sort(key=lambda x: (x.virality_score, x.view_count), reverse=True)
            items = processed_items[:limit]

        except Exception as exc:
            logger.error("Erro na busca do YouTube Shorts: %s", exc)

        return items

    async def search(self, filter_params: DiscoveryFilter) -> List[DiscoveryItem]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._search_sync, filter_params.query, filter_params.limit)

    async def health_check(self) -> bool:
        return True
