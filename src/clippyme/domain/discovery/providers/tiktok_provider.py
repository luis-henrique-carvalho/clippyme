from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.parse
import urllib.error

from ..base import DiscoveryProvider
from ..schemas import DiscoveryFilter, DiscoveryItem, PlatformType
from ..scoring import calculate_virality_score, calculate_engagement_rate, calculate_view_velocity

logger = logging.getLogger("clippyme.discovery.tiktok")


class TikTokProvider(DiscoveryProvider):
    """Provedor de busca e descoberta de vídeos do TikTok."""

    @property
    def platform(self) -> PlatformType:
        return PlatformType.TIKTOK

    def _search_sync(self, query: str, limit: int = 20) -> List[DiscoveryItem]:
        clean_tag = query.strip().lstrip("#").replace(" ", "")
        items: List[DiscoveryItem] = []
        now = int(time.time())

        # 1. Tenta extração de tag via yt-dlp
        try:
            import yt_dlp
            tag_url = f"https://www.tiktok.com/tag/{clean_tag}"
            ydl_opts = {
                "extract_flat": True,
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "playlistend": limit,
            }
            from clippyme.domain.cookie_resolver import resolve_platform_cookies
            cookies_path = resolve_platform_cookies("tiktok")
            if cookies_path:
                ydl_opts["cookiefile"] = cookies_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(tag_url, download=False)
                if info and "entries" in info:
                    for entry in info["entries"]:
                        if not entry:
                            continue
                        video_id = entry.get("id")
                        if not video_id:
                            continue

                        url = entry.get("url") or f"https://www.tiktok.com/@user/video/{video_id}"
                        title = entry.get("title") or f"TikTok Video {video_id}"
                        uploader = entry.get("uploader") or entry.get("channel") or "TikTok Creator"
                        uploader_id = entry.get("uploader_id") or uploader
                        views = int(entry.get("view_count") or 0)
                        likes = int(entry.get("like_count") or 0)
                        comments = int(entry.get("comment_count") or 0)
                        shares = int(entry.get("repost_count") or 0)
                        timestamp = entry.get("timestamp")
                        thumbnail = entry.get("thumbnail")

                        virality = calculate_virality_score(
                            platform=PlatformType.TIKTOK,
                            views=views,
                            likes=likes,
                            comments=comments,
                            shares=shares,
                            published_timestamp=timestamp,
                            current_timestamp=now,
                        )

                        item = DiscoveryItem(
                            id=video_id,
                            platform=PlatformType.TIKTOK,
                            url=url,
                            title=title[:120],
                            description=title,
                            author_name=uploader,
                            author_handle=f"@{uploader_id}" if not str(uploader_id).startswith("@") else str(uploader_id),
                            published_timestamp=timestamp,
                            thumbnail_url=thumbnail,
                            view_count=views,
                            like_count=likes,
                            comment_count=comments,
                            share_count=shares,
                            virality_score=virality,
                            engagement_rate=calculate_engagement_rate(PlatformType.TIKTOK, views, likes, comments, shares),
                            view_velocity=calculate_view_velocity(views, timestamp, now),
                        )
                        items.append(item)
                        if len(items) >= limit:
                            break
        except Exception as exc:
            logger.warning("Erro na busca de TikTok via tag: %s", exc)

        return items

    async def search(self, filter_params: DiscoveryFilter) -> List[DiscoveryItem]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._search_sync, filter_params.query, filter_params.limit)

    async def health_check(self) -> bool:
        return True
