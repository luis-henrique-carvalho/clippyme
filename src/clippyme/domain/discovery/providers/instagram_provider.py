from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.parse
import urllib.error

from ..base import DiscoveryProvider
from ..schemas import DiscoveryFilter, DiscoveryItem, PlatformType
from ..scoring import calculate_virality_score, calculate_engagement_rate, calculate_view_velocity

logger = logging.getLogger("clippyme.discovery.instagram")


class InstagramProvider(DiscoveryProvider):
    """Provedor de busca e descoberta de Reels e posts do Instagram."""

    @property
    def platform(self) -> PlatformType:
        return PlatformType.INSTAGRAM

    def _get_cookies_header(self) -> Optional[str]:
        """Lê os cookies salvos da plataforma para envio nos cabeçalhos."""
        from clippyme.domain.cookie_resolver import resolve_platform_cookies
        cookies_path = resolve_platform_cookies("instagram")
        if not cookies_path:
            return None
        
        cookie_pairs = []
        try:
            with open(cookies_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7 and ("instagram.com" in parts[0] or ".instagram.com" in parts[0]):
                        cookie_pairs.append(f"{parts[5]}={parts[6]}")
            if cookie_pairs:
                return "; ".join(cookie_pairs)
        except Exception as exc:
            logger.warning("Falha ao ler cookies do Instagram: %s", exc)
        return None

    def _make_request(self, url: str) -> Optional[Dict[str, Any]]:
        """Faz requisição HTTP com headers de navegador e cookies se disponíveis."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-IG-App-ID": "936619743392459",
            "X-ASBD-ID": "129477",
            "X-Requested-With": "XMLHttpRequest",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        cookie_header = self._get_cookies_header()
        if cookie_header:
            headers["Cookie"] = cookie_header

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    raw_data = response.read().decode("utf-8")
                    return json.loads(raw_data)
        except urllib.error.HTTPError as http_err:
            logger.warning("Instagram HTTP Error %s para URL %s", http_err.code, url)
        except Exception as exc:
            logger.warning("Instagram Request Error: %s", exc)
        return None

    def _search_web_internal(self, query: str, limit: int = 20) -> List[DiscoveryItem]:
        """Busca mídias através da API Web interna do Instagram."""
        clean_tag = query.strip().lstrip("#").replace(" ", "")
        items: List[DiscoveryItem] = []

        # 1. Tenta buscar informações de hashtag / top posts
        tag_url = f"https://www.instagram.com/api/v1/tags/web_info/?tag_name={urllib.parse.quote(clean_tag)}"
        data = self._make_request(tag_url)
        
        sections = []
        if data and "data" in data and "top" in data["data"]:
            sections = data["data"]["top"].get("sections", [])
        elif data and "sections" in data:
            sections = data.get("sections", [])

        now = int(time.time())

        for sec in sections:
            layout_content = sec.get("layout_content", {})
            medias = layout_content.get("medias", []) or layout_content.get("fill_items", [])
            for m_wrapper in medias:
                media = m_wrapper.get("media", m_wrapper)
                if not media:
                    continue

                code = media.get("code") or media.get("shortcode")
                if not code:
                    continue

                post_id = str(media.get("id") or code)
                is_video = bool(media.get("is_video") or media.get("media_type") == 2 or media.get("product_type") == "clips")
                if not is_video:
                    continue  # Foca em vídeos / Reels

                caption_node = media.get("caption") or {}
                caption_text = caption_node.get("text", "") if isinstance(caption_node, dict) else str(caption_node)
                title = caption_text[:120] if caption_text else f"Instagram Reel {code}"

                user = media.get("user") or {}
                author_name = user.get("full_name") or user.get("username") or "Instagram Creator"
                author_handle = f"@{user.get('username')}" if user.get("username") else "@instagram"
                author_avatar = user.get("profile_pic_url")

                views = int(media.get("play_count") or media.get("view_count") or 0)
                likes = int(media.get("like_count") or 0)
                comments = int(media.get("comment_count") or 0)
                taken_at = media.get("taken_at")
                
                # Thumbnails
                image_versions = media.get("image_versions2", {}).get("candidates", [])
                thumbnail_url = image_versions[0].get("url") if image_versions else media.get("display_url")

                url = f"https://www.instagram.com/reel/{code}/"

                virality = calculate_virality_score(
                    platform=PlatformType.INSTAGRAM,
                    views=views,
                    likes=likes,
                    comments=comments,
                    published_timestamp=taken_at,
                    current_timestamp=now,
                )
                er = calculate_engagement_rate(PlatformType.INSTAGRAM, views, likes, comments)
                velocity = calculate_view_velocity(views, taken_at, now)

                item = DiscoveryItem(
                    id=post_id,
                    platform=PlatformType.INSTAGRAM,
                    url=url,
                    title=title,
                    description=caption_text,
                    author_name=author_name,
                    author_handle=author_handle,
                    author_avatar_url=author_avatar,
                    published_timestamp=taken_at,
                    thumbnail_url=thumbnail_url,
                    view_count=views,
                    like_count=likes,
                    comment_count=comments,
                    virality_score=virality,
                    engagement_rate=er,
                    view_velocity=velocity,
                    raw_metadata={"code": code, "media_type": media.get("media_type")},
                )
                items.append(item)
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break

        return items

    def _search_via_ytdlp(self, query: str, limit: int = 20) -> List[DiscoveryItem]:
        """Fallback de extração de metadados usando yt-dlp sem baixar a mídia."""
        clean_tag = query.strip().lstrip("#").replace(" ", "")
        url = f"https://www.instagram.com/explore/tags/{clean_tag}/"
        items: List[DiscoveryItem] = []
        now = int(time.time())

        try:
            import yt_dlp
            ydl_opts = {
                "extract_flat": True,
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "playlistend": limit,
            }
            from clippyme.domain.cookie_resolver import resolve_platform_cookies
            cookies_path = resolve_platform_cookies("instagram")
            if cookies_path:
                ydl_opts["cookiefile"] = cookies_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info and "entries" in info:
                    for entry in info["entries"]:
                        if not entry:
                            continue
                        post_id = entry.get("id") or ""
                        post_url = entry.get("url") or f"https://www.instagram.com/p/{post_id}/"
                        title = entry.get("title") or f"Instagram Post {post_id}"
                        uploader = entry.get("uploader") or entry.get("channel") or "Instagram Creator"
                        views = int(entry.get("view_count") or 0)
                        likes = int(entry.get("like_count") or 0)
                        comments = int(entry.get("comment_count") or 0)
                        timestamp = entry.get("timestamp")
                        thumbnail = entry.get("thumbnail") or (entry.get("thumbnails", [{}])[0].get("url") if entry.get("thumbnails") else None)

                        virality = calculate_virality_score(
                            platform=PlatformType.INSTAGRAM,
                            views=views,
                            likes=likes,
                            comments=comments,
                            published_timestamp=timestamp,
                            current_timestamp=now,
                        )

                        item = DiscoveryItem(
                            id=post_id or str(len(items) + 1),
                            platform=PlatformType.INSTAGRAM,
                            url=post_url,
                            title=title[:120],
                            description=title,
                            author_name=uploader,
                            author_handle=f"@{uploader}",
                            published_timestamp=timestamp,
                            thumbnail_url=thumbnail,
                            view_count=views,
                            like_count=likes,
                            comment_count=comments,
                            virality_score=virality,
                            engagement_rate=calculate_engagement_rate(PlatformType.INSTAGRAM, views, likes, comments),
                            view_velocity=calculate_view_velocity(views, timestamp, now),
                        )
                        items.append(item)
                        if len(items) >= limit:
                            break
        except Exception as exc:
            logger.warning("Erro no fallback do Instagram com yt-dlp: %s", exc)

        return items

    def _search_via_index(self, query: str, limit: int = 20) -> List[DiscoveryItem]:
        """Busca Reels públicos via indexador web e hidrata os metadados."""
        items: List[DiscoveryItem] = []
        try:
            search_query = f"instagram.com/reel {query.strip().lstrip('#')}"
            data = urllib.parse.urlencode({"q": search_query}).encode("utf-8")
            req = urllib.request.Request(
                "https://html.duckduckgo.com/html/",
                data=data,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            unq = urllib.parse.unquote(html)
            codes = list(dict.fromkeys(re.findall(r"instagram\.com/reel/([A-Za-z0-9_-]+)", unq)))[:limit]

            if codes:
                now = int(time.time())
                import yt_dlp
                ydl_opts = {"extract_flat": True, "quiet": True, "skip_download": True, "no_warnings": True}
                from clippyme.domain.cookie_resolver import resolve_platform_cookies
                cookies_path = resolve_platform_cookies("instagram")
                if cookies_path:
                    ydl_opts["cookiefile"] = cookies_path

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    for code in codes:
                        url = f"https://www.instagram.com/reel/{code}/"
                        try:
                            info = ydl.extract_info(url, download=False)
                            if info:
                                title = info.get("title") or f"Instagram Reel {code}"
                                uploader = info.get("uploader") or info.get("channel") or "Instagram Creator"
                                views = int(info.get("view_count") or 0)
                                likes = int(info.get("like_count") or 0)
                                comments = int(info.get("comment_count") or 0)
                                thumb = info.get("thumbnail")
                                score = calculate_virality_score(PlatformType.INSTAGRAM, views, likes, comments, current_timestamp=now)
                                item = DiscoveryItem(
                                    id=code,
                                    platform=PlatformType.INSTAGRAM,
                                    url=url,
                                    title=title[:120],
                                    description=title,
                                    author_name=uploader,
                                    author_handle=f"@{uploader}",
                                    thumbnail_url=thumb,
                                    view_count=views,
                                    like_count=likes,
                                    comment_count=comments,
                                    virality_score=score,
                                    engagement_rate=calculate_engagement_rate(PlatformType.INSTAGRAM, views, likes, comments),
                                    view_velocity=calculate_view_velocity(views, None, now),
                                )
                                items.append(item)
                                if len(items) >= limit:
                                    break
                        except Exception:
                            continue
        except Exception as exc:
            logger.debug("Falha na busca indexada do Instagram: %s", exc)
        return items

    async def search(self, filter_params: DiscoveryFilter) -> List[DiscoveryItem]:
        loop = asyncio.get_running_loop()
        # 1. Tenta via requisições Web internas (caso haja cookies configurados)
        items = await loop.run_in_executor(None, self._search_web_internal, filter_params.query, filter_params.limit)
        
        # 2. Se não encontrou, tenta busca indexada pública
        if not items:
            items = await loop.run_in_executor(None, self._search_via_index, filter_params.query, filter_params.limit)

        # 3. Fallback final via tag yt-dlp
        if not items:
            items = await loop.run_in_executor(None, self._search_via_ytdlp, filter_params.query, filter_params.limit)
            
        return items

    async def health_check(self) -> bool:
        return True
