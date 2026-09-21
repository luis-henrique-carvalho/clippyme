import pytest
import time
from clippyme.domain.discovery.schemas import (
    DiscoveryFilter,
    DiscoveryItem,
    DiscoveryResult,
    PlatformType,
    SortOrder,
)
from clippyme.domain.discovery.scoring import (
    calculate_engagement_rate,
    calculate_freshness_decay,
    calculate_view_velocity,
    calculate_virality_score,
)
from clippyme.domain.discovery.service import DiscoveryService


def test_calculate_view_velocity():
    now = 1700000000
    published = now - 3600  # 1 hora atrás
    velocity = calculate_view_velocity(1000, published, now)
    assert velocity == 1000.0


def test_calculate_engagement_rate():
    # TikTok: likes + 2.5*comments + 4*shares + 3*saves
    er_tiktok = calculate_engagement_rate(
        PlatformType.TIKTOK, views=10000, likes=1000, comments=100, shares=50, saves=20
    )
    # (1000 + 250 + 200 + 60) / 10000 = 1510 / 10000 = 0.151
    assert pytest.approx(er_tiktok, 0.001) == 0.151

    # Instagram: likes + 3*comments + 4.5*shares
    er_ig = calculate_engagement_rate(
        PlatformType.INSTAGRAM, views=5000, likes=500, comments=50, shares=20
    )
    # (500 + 150 + 90) / 5000 = 740 / 5000 = 0.148
    assert pytest.approx(er_ig, 0.001) == 0.148


def test_calculate_freshness_decay():
    now = 1700000000
    # Zero age -> decay should be ~1.0
    decay_fresh = calculate_freshness_decay(now, 72.0, now)
    assert pytest.approx(decay_fresh, 0.01) == 1.0

    # 72 hours age -> decay should be ~0.5
    decay_72h = calculate_freshness_decay(now - 72 * 3600, 72.0, now)
    assert pytest.approx(decay_72h, 0.01) == 0.5


def test_calculate_virality_score():
    now = 1700000000
    score = calculate_virality_score(
        platform=PlatformType.INSTAGRAM,
        views=500000,
        likes=50000,
        comments=2000,
        shares=1000,
        published_timestamp=now - 3600 * 5,
        current_timestamp=now,
    )
    assert 0.0 <= score <= 100.0
    assert score > 50.0  # Vídeo muito engajado e recente deve pontuar alto


def test_discovery_schemas():
    filter_obj = DiscoveryFilter(query="politica", platform=PlatformType.INSTAGRAM, limit=10)
    assert filter_obj.query == "politica"
    assert filter_obj.platform == PlatformType.INSTAGRAM
    assert filter_obj.limit == 10

    item = DiscoveryItem(
        id="123",
        platform=PlatformType.INSTAGRAM,
        url="https://www.instagram.com/reel/abc/",
        title="Discurso",
        view_count=100000,
        like_count=10000,
        virality_score=85.5,
    )
    assert item.id == "123"
    assert item.virality_score == 85.5


def test_discovery_service_sorting():
    service = DiscoveryService()
    items = [
        DiscoveryItem(
            id="1",
            platform=PlatformType.INSTAGRAM,
            url="https://inst.com/1",
            view_count=1000,
            virality_score=50.0,
            published_timestamp=100,
        ),
        DiscoveryItem(
            id="2",
            platform=PlatformType.INSTAGRAM,
            url="https://inst.com/2",
            view_count=50000,
            virality_score=95.0,
            published_timestamp=200,
        ),
    ]

    sorted_by_viral = service._sort_items(items, SortOrder.VIRALITY_SCORE)
    assert sorted_by_viral[0].id == "2"

    sorted_by_views = service._sort_items(items, SortOrder.VIEW_COUNT)
    assert sorted_by_views[0].id == "2"
