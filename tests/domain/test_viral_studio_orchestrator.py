"""Unit tests for Viral Content Studio Lifecycle Orchestrator (Milestone 5)."""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch


import pytest

from clippyme.api.viral_studio_schemas import (
    AICopyData,
    Brand,
    ViralItem,
    VisualTemplate,
)
from clippyme.domain import (
    viral_studio_orchestrator,
    viral_studio_store,
)
from clippyme.domain.errors import ClippyMeError, NotFoundError, ValidationError


@pytest.fixture
def tmp_store_and_output(tmp_path, monkeypatch):
    """Isolated store and output directories for orchestrator testing."""
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(viral_studio_store, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(viral_studio_store, "BRANDS_FILE", None)
    monkeypatch.setattr(viral_studio_store, "TEMPLATES_FILE", None)
    monkeypatch.setattr(viral_studio_store, "BATCHES_FILE", None)
    monkeypatch.setattr(viral_studio_store, "ITEMS_FILE", None)
    monkeypatch.setenv("CLIPPYME_OUTPUT_DIR", str(output_dir))

    # Seed default brand and template
    viral_studio_store.seed_defaults(force=True)

    yield {
        "data_dir": data_dir,
        "output_dir": output_dir,
        "tmp_path": tmp_path,
    }

    viral_studio_store.reset_store()


@pytest.fixture
def dummy_video_file(tmp_path):
    video_path = tmp_path / "dummy_video.mp4"
    video_path.write_bytes(b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41")
    return str(video_path)


@pytest.mark.asyncio
async def test_process_viral_item_success(tmp_store_and_output, dummy_video_file, monkeypatch):
    """Single item execution runs through download -> copy -> render -> READY_FOR_REVIEW."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {
                "source_url": "https://www.instagram.com/reel/C_TEST1/",
                "product_code": "PROD_100",
                "manual_headline": "Headline Manual de Teste",
            }
        ],
    })
    item_id = batch["items"][0]["id"]

    # Mocks for download, copy, render
    def fake_dl(url, out_path, timeout=120):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(b"fake video data")
        return out_path

    async def fake_copy(brand, item, video_path=None):
        return AICopyData(
            product="Organizador Teste",
            product_description="Descrição",
            headlines=["H1", "H2", "H3", "H4", "H5"],
            selected_headline="H1 Selecionada",
            caption="Legenda gerada",
            hashtags=["#achadinhos"],
        )

    def fake_render(source_path, brand, template, headline, output_path, watermark=True):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"rendered video data")
        return output_path

    monkeypatch.setattr("clippyme.domain.viral_studio_download.download_viral_video", fake_dl)
    monkeypatch.setattr("clippyme.domain.viral_studio_copy.generate_affiliate_copy", fake_copy)
    monkeypatch.setattr("clippyme.domain.viral_studio_renderer.render_viral_video", fake_render)

    res = await viral_studio_orchestrator.process_viral_item(item_id)

    assert res["status"] == "READY_FOR_REVIEW"
    assert res["error_message"] is None
    assert res["source_path"] is not None
    assert os.path.exists(res["source_path"])
    assert res["rendered_path"] is not None
    assert os.path.exists(res["rendered_path"])
    assert res["selected_headline"] == "Headline Manual de Teste"
    assert res["ai_copy"] is not None


@pytest.mark.asyncio
async def test_process_viral_batch_failure_isolation(tmp_store_and_output, monkeypatch):
    """Batch execution isolates failures so failing item does not abort successful items."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {"source_url": "https://www.instagram.com/reel/C_SUCCESS_1/", "product_code": "S1"},
            {"source_url": "https://www.instagram.com/reel/C_FAIL_2/", "product_code": "F2"},
            {"source_url": "https://www.tiktok.com/@user/video/333333", "product_code": "S3"},
        ],
    })
    items = batch["items"]
    i1_id, i2_id, i3_id = items[0]["id"], items[1]["id"], items[2]["id"]

    def fake_dl(url, out_path, timeout=120):
        if "FAIL" in url:
            raise RuntimeError("Download stream not reachable")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(b"video data")
        return out_path

    async def fake_copy(brand, item, video_path=None):
        return AICopyData(
            product="Item Teste",
            product_description="Desc",
            headlines=["H1", "H2", "H3", "H4", "H5"],
            selected_headline="H1",
            caption="Caption",
            hashtags=[],
        )

    def fake_render(source_path, brand, template, headline, output_path, watermark=True):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"rendered")
        return output_path

    monkeypatch.setattr("clippyme.domain.viral_studio_download.download_viral_video", fake_dl)
    monkeypatch.setattr("clippyme.domain.viral_studio_copy.generate_affiliate_copy", fake_copy)
    monkeypatch.setattr("clippyme.domain.viral_studio_renderer.render_viral_video", fake_render)

    updated_batch = await viral_studio_orchestrator.process_viral_batch(batch["id"])

    assert updated_batch["status"] == "READY_FOR_REVIEW"
    res1 = viral_studio_store.get_item(i1_id)
    res2 = viral_studio_store.get_item(i2_id)
    res3 = viral_studio_store.get_item(i3_id)

    assert res1["status"] == "READY_FOR_REVIEW"
    assert res2["status"] == "FAILED"
    assert "Download stream not reachable" in res2["error_message"]
    assert res3["status"] == "READY_FOR_REVIEW"


@pytest.mark.asyncio
async def test_rerender_item_fast_bypass(tmp_store_and_output, dummy_video_file, monkeypatch):
    """Rerender uses existing preserved source without re-downloading."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [{"source_url": "https://www.instagram.com/reel/C_RERENDER/", "product_code": "R1"}],
    })
    item_id = batch["items"][0]["id"]
    viral_studio_store.update_item(item_id, {"source_path": dummy_video_file, "status": "READY_FOR_REVIEW"})

    render_called = False

    def fake_render(source_path, brand, template, headline, output_path, watermark=True):
        nonlocal render_called
        render_called = True
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"new render")
        return output_path

    monkeypatch.setattr("clippyme.domain.viral_studio_renderer.render_viral_video", fake_render)

    updated = await viral_studio_orchestrator.rerender_item(
        item_id=item_id,
        headline="Nova Headline Modificada! ✨",
    )

    assert render_called is True
    assert updated["status"] == "READY_FOR_REVIEW"
    assert updated["selected_headline"] == "Nova Headline Modificada! ✨"
    assert os.path.exists(updated["rendered_path"])


def test_approve_item_lifecycle_guards(tmp_store_and_output, dummy_video_file):
    """Item approval requires valid READY_FOR_REVIEW status and rendered file on disk."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [{"source_url": "https://www.instagram.com/reel/C_APP/", "product_code": "A1"}],
    })
    item_id = batch["items"][0]["id"]

    # In PENDING state -> rejects approval
    with pytest.raises(ValidationError, match="cannot be approved in state PENDING"):
        viral_studio_orchestrator.approve_item(item_id)

    # In FAILED state -> rejects approval
    viral_studio_store.update_item(item_id, {"status": "FAILED", "error_message": "Some error"})
    with pytest.raises(ValidationError, match="is FAILED and cannot be approved"):
        viral_studio_orchestrator.approve_item(item_id)

    # In READY_FOR_REVIEW with existing rendered file -> approves successfully
    rendered_file = str(tmp_store_and_output["output_dir"] / "rendered.mp4")
    with open(rendered_file, "wb") as f:
        f.write(b"valid video")
    viral_studio_store.update_item(item_id, {"status": "READY_FOR_REVIEW", "rendered_path": rendered_file})

    approved = viral_studio_orchestrator.approve_item(item_id)
    assert approved["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_publish_viral_items_workflow(tmp_store_and_output, dummy_video_file, monkeypatch):
    """Publish dispatches approved items to social publisher and updates state to PUBLISHED."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {"source_url": "https://www.instagram.com/reel/C_PUB1/", "product_code": "P1"},
            {"source_url": "https://www.instagram.com/reel/C_PUB2/", "product_code": "P2"},
        ],
    })
    i1_id = batch["items"][0]["id"]
    i2_id = batch["items"][1]["id"]

    rendered_path = str(tmp_store_and_output["output_dir"] / "rendered.mp4")
    with open(rendered_path, "wb") as f:
        f.write(b"rendered media")

    viral_studio_store.update_item(i1_id, {"status": "APPROVED", "rendered_path": rendered_path})
    viral_studio_store.update_item(i2_id, {"status": "APPROVED", "rendered_path": rendered_path})

    async def fake_publish_flow(**kwargs):
        return {
            "status": "published",
            "post_id": f"post_{uuid.uuid4().hex[:6]}",
            "platform_post_id": f"plat_{uuid.uuid4().hex[:6]}",
            "published_at": "2026-09-19T18:00:00Z",
        }

    monkeypatch.setattr("clippyme.domain.publish_service.publish_clip_flow", fake_publish_flow)

    res = await viral_studio_orchestrator.publish_viral_items(
        item_ids=[i1_id, i2_id],
        platforms=[{"platform": "instagram", "accountId": "ig_1"}],
        schedule_mode="now",
    )

    assert res["total"] == 2
    assert res["successful"] == 2
    assert res["failed"] == 0
    assert len(res["results"]) == 2

    # Check state updated in store
    assert viral_studio_store.get_item(i1_id)["status"] == "PUBLISHED"
    assert viral_studio_store.get_item(i2_id)["status"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_publish_unapproved_item_rejected(tmp_store_and_output):
    """Publishing unapproved item raises ValidationError."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [{"source_url": "https://www.instagram.com/reel/C_UNAPP/", "product_code": "U1"}],
    })
    item_id = batch["items"][0]["id"]

    with pytest.raises(ValidationError, match="not approved for publication"):
        await viral_studio_orchestrator.publish_viral_items(
            item_ids=[item_id],
            platforms=[{"platform": "instagram", "accountId": "ig_1"}],
        )


@pytest.mark.asyncio
async def test_enqueue_item_uses_shared_job_queue(tmp_store_and_output):
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [{"source_url": "https://www.instagram.com/reel/C_QUEUE/"}],
    })
    item_id = batch["items"][0]["id"]
    jobs, queue = {}, asyncio.Queue()

    job_id = await viral_studio_orchestrator.enqueue_item(
        item_id, jobs=jobs, job_queue=queue,
    )

    assert await queue.get() == job_id
    assert jobs[job_id]["job_type"] == "viral_studio"
    assert viral_studio_store.get_item(item_id)["job_id"] == job_id


@pytest.mark.asyncio
async def test_retry_rejects_approved_item(tmp_store_and_output):
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [{"source_url": "https://www.instagram.com/reel/C_NO_RETRY/"}],
    })
    item_id = batch["items"][0]["id"]
    viral_studio_store.update_item(item_id, {"status": "APPROVED"})

    with pytest.raises(ValidationError, match="cannot be retried"):
        await viral_studio_orchestrator.retry_item(item_id)


@pytest.mark.asyncio
async def test_rerender_failure_marks_item_failed(tmp_store_and_output, dummy_video_file, monkeypatch):
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [{"source_url": "https://www.instagram.com/reel/C_RENDER_FAIL/"}],
    })
    item_id = batch["items"][0]["id"]
    viral_studio_store.update_item(item_id, {"source_path": dummy_video_file})

    def fail_render(**kwargs):
        raise RuntimeError("ffmpeg exploded")

    monkeypatch.setattr("clippyme.domain.viral_studio_renderer.render_viral_video", fail_render)
    with pytest.raises(RuntimeError, match="ffmpeg exploded"):
        await viral_studio_orchestrator.rerender_item(item_id)
    assert viral_studio_store.get_item(item_id)["status"] == "FAILED"


@pytest.mark.asyncio
async def test_publish_is_idempotent_and_persists_result(tmp_store_and_output, monkeypatch):
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [{"source_url": "https://www.instagram.com/reel/C_IDEMPOTENT/"}],
    })
    item_id = batch["items"][0]["id"]
    path = tmp_store_and_output["output_dir"] / "final.mp4"
    path.write_bytes(b"video")
    viral_studio_store.update_item(item_id, {"status": "APPROVED", "rendered_path": str(path)})
    calls = 0

    async def fake_publish(**kwargs):
        nonlocal calls
        calls += 1
        return {"post_id": "post-1", "platform_post_id": "ig-1"}

    monkeypatch.setattr("clippyme.domain.publish_service.publish_clip_flow", fake_publish)
    kwargs = {"item_ids": [item_id], "platforms": [{"platform": "instagram", "accountId": "ig"}]}
    first = await viral_studio_orchestrator.publish_viral_items(**kwargs)
    second = await viral_studio_orchestrator.publish_viral_items(**kwargs)

    assert calls == 1
    assert first == second
    record = viral_studio_store.get_item(item_id)["publication_records"][0]
    assert record["result"]["post_id"] == "post-1"


@pytest.mark.asyncio
async def test_process_viral_item_persists_logs_and_context(tmp_store_and_output, dummy_video_file, monkeypatch):
    """process_viral_item records chronological structured logs and ai_context_summary on the item."""
    from clippyme.domain.viral_studio_context import VideoContext

    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {
                "source_url": "https://www.instagram.com/reel/C_LOGS_TEST/",
                "product_code": "LOG-01",
            }
        ],
    })
    item_id = batch["items"][0]["id"]

    def fake_dl(url, out_path, timeout=120):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(b"video data")
        return out_path

    fake_ctx = VideoContext(
        keyframes=[b"f1", b"f2"],
        transcript="Testando logs e observabilidade",
        original_caption="Post original #achadinho",
        title="Título Teste",
        scenes_count=2,
        has_audio=True,
        duration=15.0,
    )

    async def fake_copy(brand, item, video_path=None, video_context=None):
        return AICopyData(
            product="Produto Log",
            product_description="Desc",
            headlines=["H1", "H2", "H3", "H4", "H5"],
            selected_headline="H1",
            caption="Caption",
            hashtags=["#log"],
        )

    def fake_render(source_path, brand, template, headline, output_path, watermark=True):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"rendered")
        return output_path

    monkeypatch.setattr("clippyme.domain.viral_studio_download.download_viral_video", fake_dl)
    monkeypatch.setattr("clippyme.domain.viral_studio_context.extract_viral_context", lambda *a, **k: fake_ctx)
    monkeypatch.setattr("clippyme.domain.viral_studio_copy.generate_affiliate_copy", fake_copy)
    monkeypatch.setattr("clippyme.domain.viral_studio_renderer.render_viral_video", fake_render)

    res = await viral_studio_orchestrator.process_viral_item(item_id)
    assert res["status"] == "READY_FOR_REVIEW"

    item_in_store = viral_studio_store.get_item(item_id)
    assert item_in_store.get("ai_context_summary") is not None
    assert item_in_store["ai_context_summary"]["scenes_count"] == 2
    assert item_in_store["ai_context_summary"]["keyframes_count"] == 2
    assert item_in_store["ai_context_summary"]["has_audio"] is True

    logs = item_in_store.get("logs") or []
    assert len(logs) >= 5
    stages = [l["stage"] for l in logs]
    assert "INIT" in stages
    assert "DOWNLOAD" in stages
    assert "CONTEXT" in stages
    assert "AI_COPY" in stages
    assert "RENDER" in stages
    assert "COMPLETE" in stages
    # Check timestamp format
    assert all("timestamp" in l and "message" in l for l in logs)


@pytest.mark.asyncio
async def test_batch_and_item_model_propagation(tmp_store_and_output):
    """Batch and items correctly store and inherit model configuration."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "model": "ollama:llama3.2",
        "items": [
            {"source_url": "https://instagram.com/reel/1"},
            {"source_url": "https://instagram.com/reel/2", "model": "gemini:gemini-3.6-flash"},
        ],
    })

    assert batch["model"] == "ollama:llama3.2"
    assert batch["items"][0]["model"] == "ollama:llama3.2"
    assert batch["items"][1]["model"] == "gemini:gemini-3.6-flash"

    # Test update_item with model
    updated = viral_studio_store.update_item(batch["items"][0]["id"], {"model": "gemini:gemini-3.5-flash-lite"})
    assert updated["model"] == "gemini:gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_process_viral_item_passes_model_to_copy(tmp_store_and_output, monkeypatch):
    """process_viral_item forwards item/batch model to generate_affiliate_copy."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "model": "ollama:llama3.2",
        "items": [
            {"source_url": "https://instagram.com/reel/MODEL_TEST"},
        ],
    })
    item_id = batch["items"][0]["id"]

    captured_model = []

    def fake_dl(url, out_path, timeout=120):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(b"video data")
        return out_path

    async def fake_copy(brand, item, video_path=None, video_context=None, model=None):
        captured_model.append(model)
        return AICopyData(
            product="Produto",
            product_description="Desc",
            headlines=["H1", "H2", "H3", "H4", "H5"],
            selected_headline="H1",
            caption="Caption",
            hashtags=[],
        )

    def fake_render(source_path, brand, template, headline, output_path, watermark=True):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"rendered")
        return output_path

    monkeypatch.setattr("clippyme.domain.viral_studio_download.download_viral_video", fake_dl)
    monkeypatch.setattr("clippyme.domain.viral_studio_copy.generate_affiliate_copy", fake_copy)
    monkeypatch.setattr("clippyme.domain.viral_studio_renderer.render_viral_video", fake_render)

    res = await viral_studio_orchestrator.process_viral_item(item_id)
    assert res["status"] == "READY_FOR_REVIEW"
    assert captured_model == ["ollama:llama3.2"]


@pytest.mark.asyncio
async def test_process_viral_item_records_ai_routing_and_ai_error(tmp_store_and_output, monkeypatch):
    """process_viral_item logs AI_ROUTING and on error logs AI_ERROR and sets status FAILED."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "model": "lmstudio:google/gemma-4-12b-qat",
        "items": [
            {"source_url": "https://instagram.com/reel/ERR_TEST"},
        ],
    })
    item_id = batch["items"][0]["id"]

    def fake_dl(url, out_path, timeout=120):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(b"video data")
        return out_path

    async def fake_copy_fail(*args, **kwargs):
        raise ClippyMeError("Cannot connect to LM Studio at http://localhost:1234")

    monkeypatch.setattr("clippyme.domain.viral_studio_download.download_viral_video", fake_dl)
    monkeypatch.setattr("clippyme.domain.viral_studio_copy.generate_affiliate_copy", fake_copy_fail)

    res = await viral_studio_orchestrator.process_viral_item(item_id)
    assert res["status"] == "FAILED"
    assert "Cannot connect to LM Studio" in res["error_message"]

    item_in_store = viral_studio_store.get_item(item_id)
    logs = item_in_store.get("logs") or []
    stages = [l["stage"] for l in logs]
    assert "AI_ROUTING" in stages
    assert "AI_ERROR" in stages
    ai_routing_log = next(l for l in logs if l["stage"] == "AI_ROUTING")
    assert ai_routing_log["details"]["provider"] == "lmstudio"
    assert ai_routing_log["details"]["target_model"] == "google/gemma-4-12b-qat"


@pytest.mark.asyncio
async def test_regenerate_item_copy_success(tmp_store_and_output, monkeypatch):
    """regenerate_item_copy updates copy, telemetry, and logs on an existing item."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {"source_url": "https://instagram.com/reel/REGEN_TEST", "product_code": "PROD-10"},
        ],
    })
    item_id = batch["items"][0]["id"]
    viral_studio_store.update_item(item_id, {
        "status": "READY_FOR_REVIEW",
        "selected_headline": "Old Headline",
        "caption": "Old Caption",
        "ai_copy": {
            "product": "Old Prod",
            "headlines": ["Old Headline"],
            "selected_headline": "Old Headline",
            "caption": "Old Caption",
            "hashtags": ["#old"],
        },
    })

    async def fake_copy(brand, item, video_path=None, model=None, video_context=None):
        return AICopyData(
            product="Novo Produto Regerado",
            product_description="Descricao nova",
            headlines=["Nova Headline 1", "Nova Headline 2", "Nova Headline 3", "Nova Headline 4", "Nova Headline 5"],
            selected_headline="Nova Headline 1",
            caption="Nova Legenda Regerada 📌 Produto PROD-10",
            hashtags=["#novo", "#achadinhos"],
        )

    monkeypatch.setattr("clippyme.domain.viral_studio_copy.generate_affiliate_copy", fake_copy)

    res = await viral_studio_orchestrator.regenerate_item_copy(
        item_id,
        model="lmstudio:google/gemma-4-12b-qat",
        manual_instructions="Focar na durabilidade",
    )

    assert res["selected_headline"] == "Nova Headline 1"
    assert "Nova Legenda Regerada" in res["caption"]
    assert res["ai_copy"]["product"] == "Novo Produto Regerado"
    assert res["model"] == "lmstudio:google/gemma-4-12b-qat"
    assert res["manual_instructions"] == "Focar na durabilidade"

    item_in_store = viral_studio_store.get_item(item_id)
    assert item_in_store["selected_headline"] == "Nova Headline 1"
    logs = item_in_store.get("logs") or []
    stages = [l["stage"] for l in logs]
    assert "AI_ROUTING" in stages
    assert "AI_COPY" in stages


@pytest.mark.asyncio
async def test_regenerate_item_copy_overwrites_stale_headlines_end_to_end(tmp_store_and_output, monkeypatch):
    """regenerate_item_copy must overwrite existing selected_headline and caption with new LLM output."""
    batch = viral_studio_store.create_batch({
        "brand_id": "vale-o-clique",
        "items": [
            {"source_url": "https://instagram.com/reel/REAL_REGEN", "product_code": "PROD-99"},
        ],
    })
    item_id = batch["items"][0]["id"]
    viral_studio_store.update_item(item_id, {
        "status": "READY_FOR_REVIEW",
        "manual_headline": "Old Manual Headline",
        "selected_headline": "Old Manual Headline",
        "caption": "Old Stale Caption",
        "ai_copy": {
            "product": "Old Prod",
            "headlines": ["Old Manual Headline"],
            "selected_headline": "Old Manual Headline",
            "caption": "Old Stale Caption",
            "hashtags": ["#old"],
        },
    })

    fake_llm_json = json.dumps({
        "product": "Produto Fresco e Novo",
        "product_description": "Nova descricao",
        "headlines": [
            "Headline Fresca 1",
            "Headline Fresca 2",
            "Headline Fresca 3",
            "Headline Fresca 4",
            "Headline Fresca 5",
        ],
        "selected_headline": "Headline Fresca 1",
        "caption": "Nova Legenda Fresca 📌 Produto PROD-99",
        "hashtags": ["#novo", "#achadinhos"],
    })

    class FakeResponse:
        def getcode(self):
            return 200
        def read(self):
            return json.dumps({
                "choices": [{
                    "message": {"content": fake_llm_json}
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
            }).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=120: FakeResponse())

    res = await viral_studio_orchestrator.regenerate_item_copy(
        item_id,
        model="lmstudio:google/gemma-4-12b-qat",
        manual_instructions="Instrucao nova",
    )

    # Must NOT keep "Old Manual Headline" or "Old Stale Caption"
    assert res["selected_headline"] == "Headline Fresca 1"
    assert res["caption"] == "Nova Legenda Fresca 📌 Produto PROD-99"
    assert res["ai_copy"]["product"] == "Produto Fresco e Novo"
    assert res["manual_instructions"] == "Instrucao nova"




