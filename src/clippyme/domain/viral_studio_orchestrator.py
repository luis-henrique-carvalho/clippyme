"""Async batch lifecycle orchestrator for Viral Content Studio (Milestone 5).

Coordinates:
- Bounded concurrency execution via asyncio.Semaphore (MAX_CONCURRENT_JOBS)
- Per-item state lifecycle: PENDING -> DOWNLOADING -> ANALYZING -> RENDERING -> READY_FOR_REVIEW
- Strict per-item failure isolation (failed items transition to FAILED without aborting the batch)
- Fast re-render bypass (rerender_item reuses cached downloads/copy without redundant I/O)
- Item approval gating (transitions READY_FOR_REVIEW -> APPROVED, rejecting unrendered/failed items)
- Zernio social publishing integration (publish_viral_items dispatches approved items)
- Reprocess/retry of failed items
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any, Dict, List, Optional

from clippyme.api.viral_studio_schemas import (
    DEFAULT_BRAND,
    DEFAULT_TEMPLATE,
    Brand,
    ViralItem,
    VisualTemplate,
)
from clippyme.domain import (
    viral_studio_context,
    viral_studio_copy,
    viral_studio_download,
    viral_studio_renderer,
    viral_studio_store,
)
from clippyme.domain.errors import ConflictError, NotFoundError, ValidationError
from clippyme.domain.job_submission import submit_job

logger = logging.getLogger("clippyme.viral_studio_orchestrator")


def append_item_log(
    item_id: str,
    stage: str,
    message: str,
    level: str = "info",
    details: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Append a structured log entry to the item's activity history and persist."""
    log_entry: Dict[str, Any] = {
        "timestamp": datetime.now(dt_timezone.utc).isoformat(),
        "stage": stage,
        "level": level,
        "message": message,
    }
    if details:
        log_entry["details"] = details
    try:
        item = viral_studio_store.get_item(item_id)
        if item:
            logs = list(item.get("logs") or [])
            logs.append(log_entry)
            viral_studio_store.update_item(item_id, {"logs": logs})
            return logs
    except Exception as exc:
        logger.debug("Could not persist log for item %s: %s", item_id, exc)
    return [log_entry]

def _get_output_dir() -> str:
    return os.environ.get("CLIPPYME_OUTPUT_DIR") or "output"


def _resolve_source_path(batch_id: str, item_id: str) -> str:
    return os.path.join(_get_output_dir(), "viral_studio", batch_id, item_id, "source.mp4")


def _resolve_render_path(batch_id: str, item_id: str) -> str:
    return os.path.join(_get_output_dir(), "viral_studio", batch_id, item_id, "rendered.mp4")


async def enqueue_item(
    item_id: str, *, jobs: dict, job_queue: asyncio.Queue, on_change=None,
    rerender: bool = False, headline: Optional[str] = None,
    template_id: Optional[str] = None, watermark: Optional[bool] = None,
) -> str:
    """Submit one Viral Studio item through the application's durable queue."""
    item = viral_studio_store.get_item_or_raise(item_id)
    active_job_id = item.get("job_id")
    if active_job_id and (jobs.get(active_job_id) or {}).get("status") in {"queued", "processing", "paused"}:
        if rerender:
            raise ConflictError(f"Item {item_id} is already being processed")
        return active_job_id

    batch_id = item.get("batch_id") or "default"
    job_id = str(uuid.uuid4())
    output_dir = os.path.dirname(_resolve_source_path(batch_id, item_id))
    env = os.environ.copy()
    env["CLIPPYME_VIRAL_STUDIO_DIR"] = os.path.abspath(viral_studio_store.get_store_dir())
    env["CLIPPYME_OUTPUT_DIR"] = os.path.abspath(_get_output_dir())
    cmd = [
        os.environ.get("PYTHON", os.sys.executable),
        "-m",
        "clippyme.domain.viral_studio_orchestrator",
        "--item-id",
        item_id,
    ]
    if rerender:
        cmd.append("--rerender")
        if headline is not None:
            cmd.extend(["--headline", headline])
        if template_id is not None:
            cmd.extend(["--template-id", template_id])
        if watermark is not None:
            cmd.extend(["--watermark", str(bool(watermark)).lower()])
    await submit_job(
        jobs=jobs,
        job_queue=job_queue,
        job_id=job_id,
        cmd=cmd,
        env=env,
        job_output_dir=output_dir,
        batch=True,
        on_change=on_change,
        job_type="viral_studio",
    )
    update = {"job_id": job_id, "error_message": None}
    if rerender:
        update["status"] = "RENDERING"
    viral_studio_store.update_item(item_id, update)
    return job_id


async def enqueue_batch(
    batch: Dict[str, Any], *, jobs: dict, job_queue: asyncio.Queue, on_change=None
) -> List[str]:
    """Enqueue every batch item independently; queue capacity is authoritative."""
    submitted = []
    for item in batch.get("items", []):
        submitted.append(
            await enqueue_item(str(item["id"]), jobs=jobs, job_queue=job_queue, on_change=on_change)
        )
    return submitted


async def process_viral_item(item_id: str) -> Dict[str, Any]:
    """Execute the full 3-stage pipeline (Download -> Context/Copy -> Render) for a single item.

    Strict failure isolation: Any exception is caught and recorded as status FAILED
    with error_message on the item, without raising to the caller.
    """
    # Concurrency is owned by the shared ClippyMe job worker.  This function
    # also remains directly callable by host tests and the CLI executor.
    with contextlib.nullcontext():
        item = viral_studio_store.get_item(item_id)
        if not item:
            logger.warning("Item %s not found for processing", item_id)
            return {}

        batch_id = item.get("batch_id") or "default"
        brand_id = item.get("brand_id") or DEFAULT_BRAND.id

        try:
            brand_dict = viral_studio_store.get_brand(brand_id) or DEFAULT_BRAND.model_dump()
            template_id = (
                item.get("template_id")
                or brand_dict.get("template_id")
                or DEFAULT_TEMPLATE.id
            )
            template_dict = viral_studio_store.get_template_or_raise(template_id)

            append_item_log(
                item_id,
                "INIT",
                f"Iniciando processamento do item",
                details={"source_url": item.get("source_url"), "brand_id": brand_id, "template_id": template_id},
            )

            # ------------------------------------------------------------------
            # Stage 1: Downloader (Source Preservation & Metadata Capture)
            # ------------------------------------------------------------------
            viral_studio_store.update_item(item_id, {"status": "DOWNLOADING", "error_message": None})
            source_path = item.get("source_path")
            if not source_path or not os.path.isfile(source_path) or os.path.getsize(source_path) == 0:
                target_source_path = _resolve_source_path(batch_id, item_id)
                source_url = item.get("source_url")
                if not source_url:
                    raise ValidationError("Missing source_url on item")

                source_path = await asyncio.to_thread(
                    viral_studio_download.download_viral_video,
                    source_url,
                    target_source_path,
                )
                viral_studio_store.update_item(item_id, {"source_path": source_path})

            manifest = viral_studio_download.get_source_manifest(source_path)
            meta = manifest.get("metadata") or item.get("source_metadata") or {}
            if meta and not item.get("source_metadata"):
                viral_studio_store.update_item(item_id, {"source_metadata": meta})

            file_size_kb = round(os.path.getsize(source_path) / 1024, 1) if os.path.isfile(source_path) else 0
            res_str = ""
            try:
                from clippyme.pipeline.scene_detection import get_video_resolution
                w, h = get_video_resolution(source_path)
                if w and h:
                    res_str = f"{w}x{h}"
            except Exception:
                pass

            res_info = f", {res_str}" if res_str else ""
            append_item_log(
                item_id,
                "DOWNLOAD",
                f"Download concluído ({file_size_kb} KB{res_info})",
                details={
                    "source_path": source_path,
                    "resolution": res_str or "unknown",
                    "title": meta.get("title", ""),
                    "has_caption": bool(meta.get("description") or meta.get("caption")),
                    "uploader": meta.get("uploader", ""),
                },
            )

            # Refresh item state
            item = viral_studio_store.get_item_or_raise(item_id)

            # ------------------------------------------------------------------
            # Stage 2: Multi-Signal Context Extraction & AI Commercial Copy
            # ------------------------------------------------------------------
            viral_studio_store.update_item(item_id, {"status": "ANALYZING"})
            brand_obj = Brand.model_validate(brand_dict)
            item_obj = ViralItem.model_validate(item)

            # Extract multi-signal context
            video_context = viral_studio_context.extract_viral_context(
                video_path=source_path,
                source_metadata=item.get("source_metadata") or meta,
            )
            context_summary = video_context.to_summary_dict()
            viral_studio_store.update_item(item_id, {"ai_context_summary": context_summary})

            append_item_log(
                item_id,
                "CONTEXT",
                f"Contexto extraído: {video_context.scenes_count} cenas detectadas ({len(video_context.keyframes)} frames), áudio {'com fala identificada' if video_context.has_audio else 'sem fala/música'}",
                details=context_summary,
            )

            # A job retry must reuse successful analysis instead of spending
            # another AI request after a later render failure.
            copy_data = item.get("ai_copy")
            if not copy_data:
                try:
                    copy_data = await viral_studio_copy.generate_affiliate_copy(
                        brand=brand_obj,
                        item=item_obj,
                        video_path=source_path,
                        video_context=video_context,
                    )
                except TypeError as t_err:
                    if "video_context" in str(t_err):
                        copy_data = await viral_studio_copy.generate_affiliate_copy(
                            brand=brand_obj,
                            item=item_obj,
                            video_path=source_path,
                        )
                    else:
                        raise

            copy_headline = (
                copy_data.get("selected_headline")
                if isinstance(copy_data, dict)
                else getattr(copy_data, "selected_headline", None)
            )
            copy_caption = (
                copy_data.get("caption")
                if isinstance(copy_data, dict)
                else getattr(copy_data, "caption", None)
            )
            copy_product = (
                copy_data.get("product")
                if isinstance(copy_data, dict)
                else getattr(copy_data, "product", "Produto")
            )

            selected_headline = (
                item.get("manual_headline")
                or item.get("selected_headline")
                or copy_headline
                or "Achadinho Imperdível! 😱"
            )
            caption = (
                item.get("caption")
                or copy_caption
                or f"Confira no link!\n📌 Produto {item.get('product_code') or ''}"
            )

            viral_studio_store.update_item(
                item_id,
                {
                    "selected_headline": selected_headline,
                    "caption": caption,
                    "ai_copy": copy_data.model_dump() if hasattr(copy_data, "model_dump") else copy_data,
                    "ai_context_summary": context_summary,
                },
            )

            append_item_log(
                item_id,
                "AI_COPY",
                f"Copy comercial gerada com sucesso para '{copy_product}'",
                details={
                    "selected_headline": selected_headline,
                    "headlines_count": len(copy_data.get("headlines") if isinstance(copy_data, dict) else copy_data.headlines),
                },
            )

            # ------------------------------------------------------------------
            # Stage 3: Visual Template Rendering
            # ------------------------------------------------------------------
            viral_studio_store.update_item(item_id, {"status": "RENDERING"})
            target_render_path = _resolve_render_path(batch_id, item_id)
            template_obj = VisualTemplate.model_validate(template_dict)

            append_item_log(
                item_id,
                "RENDER",
                f"Renderizando vídeo 9:16 via FFmpeg com template '{template_obj.name}'",
                details={
                    "template_id": template_id,
                    "headline": selected_headline,
                    "resolution": f"{template_obj.width}x{template_obj.height}",
                },
            )

            rendered_path = await asyncio.to_thread(
                viral_studio_renderer.render_viral_video,
                source_path=source_path,
                brand=brand_obj,
                template=template_obj,
                headline=selected_headline,
                output_path=target_render_path,
                watermark=template_obj.watermark_enabled,
            )

            append_item_log(
                item_id,
                "COMPLETE",
                f"Vídeo renderizado com sucesso e pronto para revisão",
                details={"rendered_path": rendered_path},
            )

            # Final success state: READY_FOR_REVIEW
            updated_item = viral_studio_store.update_item(
                item_id,
                {
                    "status": "READY_FOR_REVIEW",
                    "rendered_path": rendered_path,
                    "error_message": None,
                },
            )
            logger.info("Successfully processed viral item %s -> READY_FOR_REVIEW", item_id)
            return updated_item

        except Exception as exc:
            logger.error("Failed processing viral item %s: %s", item_id, exc)
            append_item_log(
                item_id,
                "ERROR",
                f"Falha no processamento: {str(exc)}",
                level="error",
                details={"error": str(exc)},
            )
            updated_item = viral_studio_store.update_item(
                item_id,
                {
                    "status": "FAILED",
                    "error_message": str(exc),
                },
            )
            return updated_item


async def process_viral_batch(batch_id: str) -> Dict[str, Any]:
    """Process all items in a batch concurrently with failure isolation."""
    batch = viral_studio_store.get_batch(batch_id)
    if not batch:
        logger.warning("Batch %s not found for processing", batch_id)
        return {}

    items = batch.get("items", [])
    if not items:
        return batch

    tasks = []
    for it in items:
        it_id = it.get("id") or it.get("item_id")
        if it_id:
            tasks.append(process_viral_item(str(it_id)))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    # Refresh batch status
    refreshed_batch = viral_studio_store.get_batch_or_raise(batch_id)
    batch_items = refreshed_batch.get("items", [])
    all_failed = all(i.get("status") == "FAILED" for i in batch_items) if batch_items else False
    new_batch_status = "FAILED" if all_failed else "READY_FOR_REVIEW"
    viral_studio_store.update_batch(batch_id, {"status": new_batch_status})
    return viral_studio_store.get_batch_or_raise(batch_id)


async def rerender_item(
    item_id: str,
    headline: Optional[str] = None,
    template_id: Optional[str] = None,
    watermark: Optional[bool] = None,
) -> Dict[str, Any]:
    """Render an item and leave a durable failure state on any error."""
    try:
        return await _rerender_item(item_id, headline, template_id, watermark)
    except Exception as exc:
        # Keep the original domain error for the HTTP response, but never
        # strand a user-facing item in RENDERING after a failed subprocess.
        if viral_studio_store.get_item(item_id):
            append_item_log(item_id, "ERROR", f"Falha ao re-renderizar: {exc}", level="error")
            viral_studio_store.update_item(
                item_id, {"status": "FAILED", "error_message": str(exc)}
            )
        raise


async def _rerender_item(
    item_id: str,
    headline: Optional[str] = None,
    template_id: Optional[str] = None,
    watermark: Optional[bool] = None,
) -> Dict[str, Any]:
    """Fast re-render of an existing item with new headline or template without re-downloading or re-calling AI."""
    item = viral_studio_store.get_item_or_raise(item_id)
    batch_id = item.get("batch_id") or "default"
    source_path = item.get("source_path") or _resolve_source_path(batch_id, item_id)

    if not os.path.isfile(source_path) or os.path.getsize(source_path) == 0:
        source_url = item.get("source_url")
        if source_url:
            source_path = await asyncio.to_thread(
                viral_studio_download.download_viral_video,
                source_url,
                _resolve_source_path(batch_id, item_id),
            )
            viral_studio_store.update_item(item_id, {"source_path": source_path})
        else:
            raise ValidationError(f"Source video missing for item {item_id}; cannot re-render without source")

    brand_id = item.get("brand_id") or DEFAULT_BRAND.id
    brand_dict = viral_studio_store.get_brand(brand_id) or DEFAULT_BRAND.model_dump()
    brand_obj = Brand.model_validate(brand_dict)

    tpl_id = template_id or item.get("template_id") or brand_dict.get("template_id") or DEFAULT_TEMPLATE.id
    template_dict = viral_studio_store.get_template_or_raise(tpl_id)
    template_obj = VisualTemplate.model_validate(template_dict)

    render_headline = headline or item.get("selected_headline") or item.get("manual_headline") or "Achadinho"
    render_watermark = watermark if watermark is not None else template_obj.watermark_enabled

    append_item_log(
        item_id,
        "RERENDER",
        f"Iniciando re-renderização com headline: '{render_headline}'",
        details={"template_id": tpl_id, "watermark": render_watermark},
    )

    viral_studio_store.update_item(
        item_id,
        {
            "status": "RENDERING",
            "selected_headline": render_headline,
            "template_id": tpl_id,
        },
    )

    target_render_path = _resolve_render_path(batch_id, item_id)
    rendered_path = await asyncio.to_thread(
        viral_studio_renderer.render_viral_video,
        source_path=source_path,
        brand=brand_obj,
        template=template_obj,
        headline=render_headline,
        output_path=target_render_path,
        watermark=render_watermark,
    )

    append_item_log(
        item_id,
        "RERENDER_COMPLETE",
        f"Re-renderização concluída com sucesso",
        details={"rendered_path": rendered_path},
    )

    updated = viral_studio_store.update_item(
        item_id,
        {
            "status": "READY_FOR_REVIEW",
            "rendered_path": rendered_path,
            "error_message": None,
        },
    )
    return updated


def approve_item(item_id: str) -> Dict[str, Any]:
    """Transition an item from READY_FOR_REVIEW to APPROVED."""
    item = viral_studio_store.get_item_or_raise(item_id)
    status = item.get("status")

    if status == "APPROVED":
        return item

    if status == "FAILED":
        raise ValidationError(f"Item {item_id} is FAILED and cannot be approved")

    if status not in ("READY_FOR_REVIEW", "COMPLETED"):
        raise ValidationError(f"Item {item_id} cannot be approved in state {status} (must be READY_FOR_REVIEW)")

    rendered_path = item.get("rendered_path")
    if not rendered_path or not os.path.isfile(rendered_path) or os.path.getsize(rendered_path) == 0:
        raise ValidationError(f"Item {item_id} has not been rendered and cannot be approved")

    append_item_log(item_id, "APPROVE", "Item aprovado para publicação")
    return viral_studio_store.update_item(item_id, {"status": "APPROVED", "error_message": None})


async def retry_item(item_id: str) -> Dict[str, Any]:
    """Reset a failed or interrupted item and restart processing."""
    item = viral_studio_store.get_item_or_raise(item_id)
    if item.get("status") not in ("FAILED", "CANCELLED"):
        raise ValidationError(
            f"Item {item_id} cannot be retried in state {item.get('status')}"
        )
    viral_studio_store.update_item(item_id, {"status": "PENDING", "error_message": None})
    # API callers enqueue through the shared worker.  Direct callers retain a
    # deterministic state reset and can explicitly enqueue when they own one.
    return viral_studio_store.get_item_or_raise(item_id)


async def publish_viral_items(
    item_ids: List[str],
    platforms: List[Dict[str, Any]],
    schedule_mode: str = "now",
    scheduled_for: Optional[str] = None,
    timezone: Optional[str] = None,
    start_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish approved items through the shared publish flow, once per payload."""
    from clippyme.domain import publish_service
    from clippyme.storage.config_store import load_zernio_config

    config = load_zernio_config() or {}
    results = []
    for item_id in item_ids:
        item = viral_studio_store.get_item_or_raise(item_id)
        request = {
            "platforms": platforms, "schedule_mode": schedule_mode,
            "scheduled_for": scheduled_for, "timezone": timezone, "start_date": start_date,
            "title": item.get("selected_headline") or "Achadinho",
            "caption": item.get("caption") or "",
        }
        key = hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode()).hexdigest()
        cached = next(
            (record for record in item.get("publication_records") or [] if record.get("key") == key),
            None,
        )
        if cached and cached.get("status") in {"published", "scheduled"}:
            results.append(dict(cached["result"]))
            continue
        if item.get("status") != "APPROVED":
            raise ValidationError(f"Item {item_id} is not approved for publication")
        media_path = item.get("rendered_path")
        if not media_path or not os.path.isfile(media_path) or os.path.getsize(media_path) == 0:
            raise NotFoundError(f"Rendered video file not found for item {item_id}")
        reservation = viral_studio_store.reserve_publication(
            item_id, key, datetime.now(dt_timezone.utc).isoformat()
        )
        existing = reservation["record"]
        if not reservation["reserved"] and existing.get("status") in {"published", "scheduled"}:
            results.append(dict(existing["result"]))
            continue
        if not reservation["reserved"] and existing.get("status") == "dispatching":
            raise ValidationError(f"Publication for item {item_id} is awaiting reconciliation")

        try:
            published = await publish_service.publish_clip_flow(
                job_id=item.get("batch_id") or "viral_studio", clip_index=0, resolved=None,
                req={**request, "clip_path": media_path}, zernio_cfg=config,
            )
            state = "scheduled" if schedule_mode in {"auto", "manual"} else "published"
            result = {
                "item_id": item_id, "status": state, "post_id": published.get("post_id"),
                "platform_post_id": published.get("platform_post_id") or published.get("id"),
                "published_at": published.get("published_at") or datetime.now(dt_timezone.utc).isoformat(),
            }
            viral_studio_store.finish_publication(
                item_id, key, {"key": key, "status": state, "result": result},
                status="SCHEDULED" if state == "scheduled" else "PUBLISHED",
            )
            append_item_log(
                item_id,
                "PUBLISHED" if state == "published" else "SCHEDULED",
                f"Item {'publicado' if state == 'published' else 'agendado'} com sucesso na rede social",
                details=result,
            )
            results.append(result)
        except Exception as exc:
            viral_studio_store.finish_publication(
                item_id, key, {"key": key, "status": "failed", "error": str(exc)}
            )
            viral_studio_store.update_item(item_id, {"error_message": str(exc)})
            append_item_log(
                item_id,
                "PUBLISH_ERROR",
                f"Falha na publicação: {str(exc)}",
                level="error",
                details={"error": str(exc)},
            )
            results.append({"item_id": item_id, "status": "failed", "error": str(exc)})

    return {
        "results": results, "total": len(results),
        "successful": sum(r["status"] in {"published", "scheduled"} for r in results),
        "failed": sum(r["status"] == "failed" for r in results),
    }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point executed by the shared job runner."""
    parser = argparse.ArgumentParser(description="Run one Viral Studio item")
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--rerender", action="store_true")
    parser.add_argument("--headline")
    parser.add_argument("--template-id")
    parser.add_argument("--watermark", choices=("true", "false"))
    args = parser.parse_args(argv)
    item = asyncio.run(
        rerender_item(
            args.item_id, args.headline, args.template_id,
            None if args.watermark is None else args.watermark == "true",
        ) if args.rerender else process_viral_item(args.item_id)
    )
    return 1 if item.get("status") == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
