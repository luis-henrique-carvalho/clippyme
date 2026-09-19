"""Unit tests for commercial AI copy generation (Milestone 3)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clippyme.api.viral_studio_schemas import AICopyData, Brand, ViralItem
from clippyme.domain import viral_studio_copy
from clippyme.domain.errors import ClippyMeError, ValidationError


@pytest.fixture
def sample_brand():
    return Brand(
        id="vale-o-clique",
        name="Vale o Clique?",
        handle="@valeoclique",
        default_cta="Confira os achadinhos no link da bio!",
    )


@pytest.fixture
def sample_item():
    return ViralItem(
        id="item-test-01",
        batch_id="batch-01",
        brand_id="vale-o-clique",
        source_url="https://www.instagram.com/reel/C12345/",
        product_code="PROD-99",
        product_url="https://shope.ee/test99",
        additional_instructions="Destaque facilidade de limpeza",
    )


# ============================================================================
# Prompt Building Tests
# ============================================================================

def test_build_affiliate_copy_prompt_includes_brand_and_instructions(sample_brand, sample_item):
    prompt = viral_studio_copy.build_affiliate_copy_prompt(
        brand=sample_brand,
        product_code=sample_item.product_code,
        product_url=sample_item.product_url,
        manual_instructions=sample_item.additional_instructions,
    )
    assert isinstance(prompt, str)
    assert "Vale o Clique?" in prompt
    assert "@valeoclique" in prompt
    assert "Confira os achadinhos no link da bio!" in prompt
    assert "PROD-99" in prompt
    assert "https://shope.ee/test99" in prompt
    assert "Destaque facilidade de limpeza" in prompt
    assert "5 opções de headlines" in prompt
    assert "Português Brasileiro" in prompt or "PT-BR" in prompt


def test_build_affiliate_copy_prompt_works_with_dict():
    brand_dict = {
        "name": "Achadinhos da Casa",
        "handle": "@achadinhos_casa",
        "default_cta": "Link na bio!",
    }
    prompt = viral_studio_copy.build_affiliate_copy_prompt(brand_dict)
    assert "Achadinhos da Casa" in prompt
    assert "@achadinhos_casa" in prompt
    assert "Link na bio!" in prompt


def test_build_affiliate_copy_prompt_without_optional_fields(sample_brand):
    prompt = viral_studio_copy.build_affiliate_copy_prompt(sample_brand)
    assert "Vale o Clique?" in prompt
    # No crash and no 'None' literal rendered
    assert "None" not in prompt


# ============================================================================
# Response Parsing & Multi-Level JSON Repair Tests
# ============================================================================

def test_parse_affiliate_copy_response_clean_json():
    raw_json = """
    {
      "product": "Mini Selador de Embalagens",
      "product_description": "Selador térmico portátil para sacos plásticos",
      "headlines": [
        "Nunca mais coma salgadinho murcho! 😱",
        "Esse aparelhinho vai salvar seus lanches!",
        "Olha que ideia genial para fechar pacotes!",
        "Chega de usar pregador de roupa na cozinha!",
        "O melhor achadinho para fechar embalagens!"
      ],
      "selected_headline": "Nunca mais coma salgadinho murcho! 😱",
      "caption": "Nunca mais coma salgadinho murcho! 😱\\nEsse mini selador fecha tudo a vácuo.\\n📌 Produto 1020\\nConfira no link da bio!\\n#achadinhos #cozinha #dicas",
      "hashtags": ["#achadinhos", "#cozinha", "#dicas", "#utilidades"]
    }
    """
    copy_data = viral_studio_copy.parse_affiliate_copy_response(raw_json, product_code="1020")
    assert isinstance(copy_data, AICopyData)
    assert copy_data.product == "Mini Selador de Embalagens"
    assert len(copy_data.headlines) == 5
    assert copy_data.selected_headline == "Nunca mais coma salgadinho murcho! 😱"
    assert "1020" in copy_data.caption
    assert "#achadinhos" in copy_data.hashtags


def test_parse_affiliate_copy_response_markdown_fences():
    raw_markdown = """```json
    {
      "product": "Organizador Giratório 360",
      "product_description": "Organizador multiuso giratório para temperos",
      "headlines": [
        "Quem tem cozinha pequena precisa ver isso!",
        "Organize todos os temperos num só lugar!",
        "Esse organizador vai transformar sua bancada!",
        "Praticidade máxima para o seu dia a dia!",
        "Achadinho indispensável para armários!"
      ],
      "selected_headline": "Quem tem cozinha pequena precisa ver isso!",
      "caption": "Organize seus temperos de forma prática!\\nConfira na bio!",
      "hashtags": ["#organizacao", "#cozinha"]
    }
    ```"""
    copy_data = viral_studio_copy.parse_affiliate_copy_response(
        raw_markdown,
        default_cta="Confira no link da bio!",
        product_code="ORG-360",
    )
    assert copy_data.product == "Organizador Giratório 360"
    assert copy_data.selected_headline == "Quem tem cozinha pequena precisa ver isso!"
    assert "ORG-360" in copy_data.caption


def test_parse_affiliate_copy_response_repairs_trailing_commas_and_smart_quotes():
    malformed = """
    {
      “product”: “Kit Organizador”,
      “product_description”: “Caixas empilháveis transparentes”,
      “headlines”: [
        “Olha que organização perfeita!”,
        “Armário arrumado em minutos!”,
        “Diga adeus à bagunça!”,
        “Muito fácil de empilhar!”,
        “Achadinho nota 10 para casa!”,
      ],
      “selected_headline”: “Olha que organização perfeita!”,
      “caption”: “Caixas empilháveis para armários.\\nConfira na bio!”,
      “hashtags”: [“#casa”, “#decoracao”,],
    }
    """
    copy_data = viral_studio_copy.parse_affiliate_copy_response(malformed)
    assert copy_data.product == "Kit Organizador"
    assert len(copy_data.headlines) >= 5
    assert copy_data.selected_headline == "Olha que organização perfeita!"


def test_parse_affiliate_copy_response_empty_or_unparseable_uses_safe_fallback():
    # Empty string
    copy_data1 = viral_studio_copy.parse_affiliate_copy_response("", product_code="ABC-1")
    assert isinstance(copy_data1, AICopyData)
    assert len(copy_data1.headlines) == 5
    assert "ABC-1" in copy_data1.caption

    # Completely broken non-JSON text
    broken_text = "I am an AI and I cannot output JSON right now."
    copy_data2 = viral_studio_copy.parse_affiliate_copy_response(broken_text, product_code="XYZ")
    assert isinstance(copy_data2, AICopyData)
    assert len(copy_data2.headlines) == 5
    assert "XYZ" in copy_data2.caption


def test_parse_affiliate_copy_response_pads_headlines_if_fewer_than_five():
    partial_json = """
    {
      "product": "Cortador de Legumes",
      "headlines": ["Corte tudo em segundos!"]
    }
    """
    copy_data = viral_studio_copy.parse_affiliate_copy_response(partial_json)
    assert len(copy_data.headlines) == 5
    assert copy_data.headlines[0] == "Corte tudo em segundos!"
    assert copy_data.selected_headline == "Corte tudo em segundos!"


# ============================================================================
# Caching & Async Generation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_generate_affiliate_copy_respects_cache(sample_brand, sample_item):
    """If item already has ai_copy, Gemini API client is never created or called."""
    cached = AICopyData(
        product="Produto em Cache",
        product_description="Descrição em cache",
        headlines=["Headline Cache 1", "Headline Cache 2", "Headline Cache 3", "Headline Cache 4", "Headline Cache 5"],
        selected_headline="Headline Cache 1",
        caption="Legenda já gerada",
        hashtags=["#cache"],
    )
    sample_item.ai_copy = cached

    with patch("google.genai.Client") as mock_client:
        result = await viral_studio_copy.generate_affiliate_copy(sample_brand, sample_item)
        assert result == cached
        assert not mock_client.called


@pytest.mark.asyncio
async def test_generate_affiliate_copy_success_and_caches_on_item(sample_brand, sample_item):
    """When uncached, calls Gemini, parses response, and sets item.ai_copy."""
    mock_resp_json = """
    {
      "product": "Suporte Adesivo Multiuso",
      "product_description": "Suporte sem furar parede",
      "headlines": [
        "Chega de furar parede na sua casa! 😱",
        "Olha que suporte resistente e prático!",
        "Aguenta muito peso e não estraga a parede!",
        "Muito fácil de instalar na cozinha ou banheiro!",
        "O achadinho que todo inquilino precisa!"
      ],
      "selected_headline": "Chega de furar parede na sua casa! 😱",
      "caption": "Chega de furar parede!\\n📌 Produto PROD-99\\nConfira na bio!\\n#achadinhos #dicas",
      "hashtags": ["#achadinhos", "#dicas", "#casa"]
    }
    """
    mock_resp = MagicMock()
    mock_resp.text = mock_resp_json

    mock_models = AsyncMock()
    mock_models.generate_content.return_value = mock_resp

    mock_client = MagicMock()
    mock_client.aio.models = mock_models

    with patch("google.genai.Client", return_value=mock_client):
        copy_res = await viral_studio_copy.generate_affiliate_copy(
            sample_brand,
            sample_item,
            api_key="test-api-key-123",
        )

        assert copy_res.product == "Suporte Adesivo Multiuso"
        assert copy_res.selected_headline == "Chega de furar parede na sua casa! 😱"
        assert sample_item.ai_copy is not None
        assert sample_item.ai_copy.product == "Suporte Adesivo Multiuso"
        assert sample_item.selected_headline == "Chega de furar parede na sua casa! 😱"


@pytest.mark.asyncio
async def test_generate_affiliate_copy_model_fallback(sample_brand, sample_item):
    """If the primary model fails, the client falls back to the next model."""
    mock_resp = MagicMock()
    mock_resp.text = """
    {
      "product": "Produto Fallback",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": "Legenda fallback",
      "hashtags": ["#fb"]
    }
    """

    mock_models = AsyncMock()
    # First model raises error, second model returns valid response
    mock_models.generate_content.side_effect = [
        RuntimeError("Primary model 404 not found"),
        mock_resp,
    ]

    mock_client = MagicMock()
    mock_client.aio.models = mock_models

    with patch("google.genai.Client", return_value=mock_client):
        result = await viral_studio_copy.generate_affiliate_copy(
            sample_brand,
            sample_item,
            api_key="test-key",
            model="gemini-3.5-flash",
        )
        assert result.product == "Produto Fallback"
        assert mock_models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_generate_affiliate_copy_raises_validation_error_on_missing_key(sample_brand, sample_item):
    with patch("clippyme.storage.config_store.load_persistent_config", return_value={"GEMINI_API_KEY": ""}), \
         patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=True):
        with pytest.raises(ValidationError) as exc:
            await viral_studio_copy.generate_affiliate_copy(sample_brand, sample_item)
        assert "Gemini API key is not configured" in str(exc.value)


@pytest.mark.asyncio
async def test_generate_affiliate_copy_manual_headline_precedence(sample_brand):
    """If manual_headline is set on item, it takes precedence in selected_headline."""
    item = ViralItem(
        id="item-manual",
        source_url="https://www.instagram.com/reel/123/",
        manual_headline="Headline Feita Manualmente Pelo Criador!",
    )
    mock_resp = MagicMock()
    mock_resp.text = """
    {
      "product": "Produto Teste",
      "headlines": ["Opcao 1", "Opcao 2", "Opcao 3", "Opcao 4", "Opcao 5"],
      "selected_headline": "Opcao 1",
      "caption": "Legenda teste",
      "hashtags": ["#teste"]
    }
    """
    mock_models = AsyncMock()
    mock_models.generate_content.return_value = mock_resp
    mock_client = MagicMock()
    mock_client.aio.models = mock_models

    with patch("google.genai.Client", return_value=mock_client):
        res = await viral_studio_copy.generate_affiliate_copy(sample_brand, item, api_key="dummy")
        assert res.selected_headline == "Headline Feita Manualmente Pelo Criador!"
        assert "Headline Feita Manualmente Pelo Criador!" in res.headlines


@pytest.mark.asyncio
async def test_generate_affiliate_copy_with_raw_dict_item(sample_brand):
    """generate_affiliate_copy supports item passed as a dict."""
    item_dict = {
        "id": "dict-item-01",
        "source_url": "https://www.tiktok.com/@u/video/123",
        "product_code": "PROD-DICT",
    }
    mock_resp = MagicMock()
    mock_resp.text = """
    {
      "product": "Produto em Dict",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": "Legenda dict com produto PROD-DICT",
      "hashtags": ["#dict"]
    }
    """
    mock_models = AsyncMock()
    mock_models.generate_content.return_value = mock_resp
    mock_client = MagicMock()
    mock_client.aio.models = mock_models

    with patch("google.genai.Client", return_value=mock_client):
        res = await viral_studio_copy.generate_affiliate_copy(sample_brand, item_dict, api_key="dummy")
        assert res.product == "Produto em Dict"
        assert item_dict.get("ai_copy") is not None
        assert item_dict["ai_copy"]["product"] == "Produto em Dict"


def test_parse_affiliate_copy_response_unusual_types_in_json():
    """Non-string/numeric types in JSON fields are coerced or safely handled."""
    weird_json = """
    {
      "product": 12345,
      "product_description": null,
      "headlines": ["Boa headline 1", 999, null, "Boa headline 2"],
      "selected_headline": null,
      "caption": null,
      "hashtags": ["achadinhos", "#dicas", "cozinha legal"]
    }
    """
    copy = viral_studio_copy.parse_affiliate_copy_response(weird_json, default_cta="Clique aqui!")
    assert copy.product == "12345"
    assert len(copy.headlines) >= 5
    assert copy.selected_headline in copy.headlines
    # Hashtags normalized with # and no internal space
    assert all(t.startswith("#") for t in copy.hashtags)
    assert "#achadinhos" in copy.hashtags
    assert "#cozinhalegal" in copy.hashtags


def test_parse_affiliate_copy_response_excessive_headlines_truncated():
    """Headlines array exceeding 10 items is capped at 10."""
    many_headlines = [f"Headline {i}" for i in range(15)]
    data = {
        "product": "Produto Teste",
        "headlines": many_headlines,
        "selected_headline": "Headline 0",
        "caption": "Legenda",
        "hashtags": ["#teste"],
    }
    import json
    copy = viral_studio_copy.parse_affiliate_copy_response(json.dumps(data))
    assert len(copy.headlines) == 10


@pytest.mark.asyncio
async def test_generate_affiliate_copy_all_models_fail_raises_clippyme_error(sample_brand, sample_item):
    """When every candidate model in fallback chain raises, raises ClippyMeError."""
    mock_models = AsyncMock()
    mock_models.generate_content.side_effect = RuntimeError("All models unavailable")
    mock_client = MagicMock()
    mock_client.aio.models = mock_models

    with patch("google.genai.Client", return_value=mock_client):
        with pytest.raises(ClippyMeError) as exc:
            await viral_studio_copy.generate_affiliate_copy(sample_brand, sample_item, api_key="dummy")
        assert "failed" in str(exc.value).lower()

