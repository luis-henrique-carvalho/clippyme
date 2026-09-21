"""Unit tests for commercial AI copy generation (Milestone 3)."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clippyme.api.viral_studio_schemas import AICopyData, Brand, ViralItem
from clippyme.domain import viral_studio_copy
from clippyme.domain.errors import ClippyMeError, ValidationError


@pytest.fixture(autouse=True)
def isolate_config(monkeypatch):
    monkeypatch.setattr("clippyme.domain.viral_studio_copy.load_persistent_config", lambda: {})


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

def test_generate_affiliate_copy_respects_cache(sample_brand, sample_item):
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
        result = asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, sample_item))
        assert result == cached
        assert not mock_client.called


def test_generate_affiliate_copy_success_and_caches_on_item(sample_brand, sample_item):
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
        copy_res = asyncio.run(viral_studio_copy.generate_affiliate_copy(
            sample_brand,
            sample_item,
            api_key="test-api-key-123",
        ))

        assert copy_res.product == "Suporte Adesivo Multiuso"
        assert copy_res.selected_headline == "Chega de furar parede na sua casa! 😱"
        assert sample_item.ai_copy is not None
        assert sample_item.ai_copy.product == "Suporte Adesivo Multiuso"
        assert sample_item.selected_headline == "Chega de furar parede na sua casa! 😱"


def test_generate_affiliate_copy_model_fallback(sample_brand, sample_item):
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
        result = asyncio.run(viral_studio_copy.generate_affiliate_copy(
            sample_brand,
            sample_item,
            api_key="test-key",
            model="gemini-3.5-flash",
        ))
        assert result.product == "Produto Fallback"
        assert mock_models.generate_content.call_count == 2


def test_generate_affiliate_copy_raises_validation_error_on_missing_key(sample_brand, sample_item):
    sample_item.ai_copy = None
    with patch("clippyme.domain.viral_studio_copy.load_persistent_config", return_value={"GEMINI_API_KEY": ""}), \
         patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=True):
        with pytest.raises(ValidationError) as exc:
            asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, sample_item))
        assert "Gemini API key is not configured" in str(exc.value)


def test_generate_affiliate_copy_manual_headline_precedence(sample_brand):
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
        res = asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, item, api_key="dummy"))
        assert res.selected_headline == "Headline Feita Manualmente Pelo Criador!"
        assert "Headline Feita Manualmente Pelo Criador!" in res.headlines


def test_generate_affiliate_copy_with_raw_dict_item(sample_brand):
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
        res = asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, item_dict, api_key="dummy"))
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


def test_generate_affiliate_copy_all_models_fail_raises_clippyme_error(sample_brand, sample_item):
    """When every candidate model in fallback chain raises, raises ClippyMeError."""
    mock_models = AsyncMock()
    mock_models.generate_content.side_effect = RuntimeError("All models unavailable")
    mock_client = MagicMock()
    mock_client.aio.models = mock_models

    with patch("google.genai.Client", return_value=mock_client):
        with pytest.raises(ClippyMeError) as exc:
            asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, sample_item, api_key="dummy"))
        assert "failed" in str(exc.value).lower()


# ============================================================================
# Adversarial & Edge-Case Tests (Round 1 Hardening)
# ============================================================================

def test_generate_affiliate_copy_honors_manual_headline_on_cache_hit(sample_brand):
    """When item.ai_copy is cached but manual_headline is updated, returns updated headline."""
    cached_copy = AICopyData(
        product="Produto Inicial",
        product_description="Descricao inicial",
        headlines=["Original 1", "Original 2", "Original 3", "Original 4", "Original 5"],
        selected_headline="Original 1",
        caption="Legenda inicial",
        hashtags=["#inicial"],
    )
    item = ViralItem(
        id="item-cached-01",
        source_url="https://instagram.com/reel/123",
        ai_copy=cached_copy,
        manual_headline="Headline Atualizada Manualmente!",
    )
    # Call generate_affiliate_copy without mocking Gemini - should hit cache
    result = asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, item))
    assert result.selected_headline == "Headline Atualizada Manualmente!"
    assert "Headline Atualizada Manualmente!" in result.headlines


def test_generate_affiliate_copy_preserves_custom_caption_in_store(sample_brand):
    """Custom caption on item is not overwritten in store by newly generated AI copy."""
    item = ViralItem(
        id="item-store-preserve-01",
        source_url="https://instagram.com/reel/123",
        caption="Minha Legenda Customizada Pelo Usuario 123",
    )

    mock_resp = MagicMock()
    mock_resp.text = """{
      "product": "Produto Novo",
      "product_description": "Descricao nova",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": "Legenda Gerada Pela IA",
      "hashtags": ["#ia"]
    }"""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    with patch("google.genai.Client", return_value=mock_client), \
         patch("clippyme.domain.viral_studio_store.update_item") as mock_update:
        asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, item, api_key="test-key"))

        mock_update.assert_called_once()
        patch_payload = mock_update.call_args[0][1]
        assert patch_payload["caption"] == "Minha Legenda Customizada Pelo Usuario 123"
        assert item.caption == "Minha Legenda Customizada Pelo Usuario 123"


def test_build_affiliate_copy_prompt_includes_brand_tone_and_guardrails(sample_brand):
    """Prompt includes brand tone and explicit anti-automation guardrails."""
    sample_brand_dict = {
        "name": "Achadinhos Premium",
        "handle": "@achadinhos_premium",
        "default_cta": "Veja no link!",
        "tone": "Elegante e descontraído",
    }
    prompt = viral_studio_copy.build_affiliate_copy_prompt(sample_brand_dict)
    assert "Tom de voz da marca: Elegante e descontraído" in prompt
    assert "Comente QUERO" in prompt
    assert "NUNCA" in prompt


def test_parse_affiliate_copy_response_literal_newlines_in_json():
    """JSON with raw unescaped newlines inside strings parses cleanly."""
    raw = """{
      "product": "Organizador Multiuso",
      "product_description": "Organizador resistente",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": "Linha 1 de gancho
Linha 2 de benefício
Linha 3 com chamada",
      "hashtags": ["#achadinhos"]
    }"""
    copy_data = viral_studio_copy.parse_affiliate_copy_response(raw)
    assert copy_data.product == "Organizador Multiuso"
    assert "Linha 1 de gancho" in copy_data.caption
    assert "Linha 2 de benefício" in copy_data.caption


def test_parse_affiliate_copy_response_whitespace_product_code():
    """Empty or whitespace-only product code does not insert blank code prefix."""
    raw = """{
      "product": "Organizador",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": "Gancho incrível!",
      "hashtags": ["#achadinhos"]
    }"""
    copy_data = viral_studio_copy.parse_affiliate_copy_response(raw, product_code="   ")
    assert "📌 Produto" not in copy_data.caption


def test_parse_affiliate_copy_response_string_hashtags():
    """Hashtags returned as a single string are parsed into a normalized list, not overwritten with fallbacks."""
    raw = """{
      "product": "Mini Processador",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": "Pique tudo em segundos!",
      "hashtags": "#achadinhos #cozinha #praticidade"
    }"""
    copy_data = viral_studio_copy.parse_affiliate_copy_response(raw)
    assert copy_data.hashtags == ["#achadinhos", "#cozinha", "#praticidade"]


def test_parse_affiliate_copy_response_list_caption():
    """Caption returned as a list of paragraphs is cleanly joined with newlines."""
    raw = """{
      "product": "Dispenser de Detergente",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": [
        "Economize sabão na cozinha!",
        "Muito prático e não molha a pia.",
        "Confira o link na bio!"
      ],
      "hashtags": ["#achadinhos"]
    }"""
    copy_data = viral_studio_copy.parse_affiliate_copy_response(raw)
    assert "Economize sabão na cozinha!" in copy_data.caption
    assert "Muito prático e não molha a pia." in copy_data.caption
    assert "[" not in copy_data.caption
    assert "]" not in copy_data.caption


def test_parse_affiliate_copy_response_product_code_in_unrelated_text():
    """Unrelated numbers in caption do not falsely block inserting the product code callout."""
    raw = """{
      "product": "Caixas Organizadoras",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": "Temos 10 opções incríveis para a sua casa!",
      "hashtags": ["#organizacao"]
    }"""
    copy_data = viral_studio_copy.parse_affiliate_copy_response(raw, product_code="10")
    assert "📌 Produto 10" in copy_data.caption


def test_generate_affiliate_copy_cache_hit_updates_item_and_store(sample_brand):
    """Cache hit with updated manual_headline updates item in-memory and persists to store."""
    cached = AICopyData(
        product="Produto Inicial",
        headlines=["H1", "H2", "H3", "H4", "H5"],
        selected_headline="H1",
        caption="Legenda inicial",
        hashtags=["#tag"],
    )
    item = ViralItem(
        id="item-store-sync-01",
        source_url="https://instagram.com/reel/123",
        ai_copy=cached,
        manual_headline="Novo Titulo Manual do Criador",
    )

    with patch("clippyme.domain.viral_studio_store.update_item") as mock_update:
        res = asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, item))
        assert res.selected_headline == "Novo Titulo Manual do Criador"
        assert item.selected_headline == "Novo Titulo Manual do Criador"
        mock_update.assert_called_once()
        payload = mock_update.call_args[0][1]
        assert payload["selected_headline"] == "Novo Titulo Manual do Criador"


def test_generate_affiliate_copy_returns_coherent_custom_copy(sample_brand):
    """Returned AICopyData reflects custom caption and headline set on the item."""
    item = ViralItem(
        id="item-custom-copy-01",
        source_url="https://instagram.com/reel/123",
        caption="Minha Legenda Customizada Pelo Usuario 999",
        selected_headline="Headline Customizada Previa",
    )
    mock_resp = MagicMock()
    mock_resp.text = """{
      "product": "Produto Novo",
      "headlines": ["IA 1", "IA 2", "IA 3", "IA 4", "IA 5"],
      "selected_headline": "IA 1",
      "caption": "Legenda da IA que nao deve substituir a do usuario",
      "hashtags": ["#ia"]
    }"""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    with patch("google.genai.Client", return_value=mock_client), \
         patch("clippyme.domain.viral_studio_store.update_item"):
        result = asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, item, api_key="test-key"))
        assert result.caption == "Minha Legenda Customizada Pelo Usuario 999"
        assert result.selected_headline == "Headline Customizada Previa"
        assert "Headline Customizada Previa" in result.headlines


def test_generate_affiliate_copy_resolves_os_environ_api_key(sample_brand):
    """API key is resolved from os.environ when config.json has empty string."""
    item = ViralItem(id="item-env-key", source_url="https://instagram.com/reel/123")
    mock_resp = MagicMock()
    mock_resp.text = """{
      "product": "Produto Env",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": "Legenda",
      "hashtags": ["#tag"]
    }"""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    with patch("clippyme.domain.viral_studio_copy.load_persistent_config", return_value={"GEMINI_API_KEY": ""}), \
         patch.dict("os.environ", {"GEMINI_API_KEY": "AIzaSyTestEnvKey12345678901234567890123"}), \
         patch("google.genai.Client", return_value=mock_client) as mock_cls, \
         patch("clippyme.domain.viral_studio_store.update_item"):
        res = asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, item))
        assert res.product == "Produto Env"
        mock_cls.assert_called_once_with(api_key="AIzaSyTestEnvKey12345678901234567890123")


def test_parse_affiliate_copy_response_ten_headlines_with_unseen_selected_headline_does_not_exceed_max_length():
    """When Gemini returns 10 headlines and an unseen selected_headline, list is strictly capped at 10."""
    raw = """{
      "product": "Produto Dez Headlines",
      "headlines": [
        "Headline 1", "Headline 2", "Headline 3", "Headline 4", "Headline 5",
        "Headline 6", "Headline 7", "Headline 8", "Headline 9", "Headline 10"
      ],
      "selected_headline": "Headline Extra Inedita 11",
      "caption": "Legenda"
    }"""
    copy_data = viral_studio_copy.parse_affiliate_copy_response(raw)
    assert len(copy_data.headlines) == 10
    assert copy_data.selected_headline == "Headline Extra Inedita 11"
    assert copy_data.headlines[0] == "Headline Extra Inedita 11"
    # Pydantic validation passes without ValidationError
    assert isinstance(copy_data, AICopyData)


def test_parse_affiliate_copy_response_option_references_resolve_to_corresponding_headline():
    """Option index references like 'Opção 2', '3', 'Option 4' resolve to corresponding headline, not literal text."""
    raw_opcao_2 = """{
      "product": "Produto Teste",
      "headlines": ["Primeira H", "Segunda H Fantastica", "Terceira H", "Quarta H", "Quinta H"],
      "selected_headline": "Opção 2",
      "caption": "Legenda"
    }"""
    res2 = viral_studio_copy.parse_affiliate_copy_response(raw_opcao_2)
    assert res2.selected_headline == "Segunda H Fantastica"
    assert "Opção 2" not in res2.headlines

    raw_num_3 = """{
      "product": "Produto Teste",
      "headlines": ["Primeira H", "Segunda H", "Terceira H Fantastica", "Quarta H", "Quinta H"],
      "selected_headline": "3",
      "caption": "Legenda"
    }"""
    res3 = viral_studio_copy.parse_affiliate_copy_response(raw_num_3)
    assert res3.selected_headline == "Terceira H Fantastica"
    assert "3" not in res3.headlines

    raw_tail = """{
      "product": "Produto Teste",
      "headlines": ["Primeira H", "Segunda H", "Terceira H", "Quarta H", "Quinta H"],
      "selected_headline": "Opção 4: Headline Personalizada com Prefixo",
      "caption": "Legenda"
    }"""
    res_tail = viral_studio_copy.parse_affiliate_copy_response(raw_tail)
    assert res_tail.selected_headline == "Headline Personalizada com Prefixo"


def test_parse_affiliate_copy_response_strips_bullet_characters():
    """Headlines with bullet markers (-, *, •) have them stripped so canvas renders clean typography."""
    raw = """{
      "product": "Organizador",
      "headlines": [
        "- Primeira opcao com traco",
        "* Segunda opcao com asterisco",
        "• Terceira opcao com bullet",
        "4. Quarta opcao numerada",
        "Quinta opcao limpa"
      ],
      "selected_headline": "- Primeira opcao com traco",
      "caption": "Legenda"
    }"""
    res = viral_studio_copy.parse_affiliate_copy_response(raw)
    assert res.headlines[0] == "Primeira opcao com traco"
    assert res.headlines[1] == "Segunda opcao com asterisco"
    assert res.headlines[2] == "Terceira opcao com bullet"
    assert res.headlines[3] == "Quarta opcao numerada"
    assert res.selected_headline == "Primeira opcao com traco"


def test_parse_affiliate_copy_response_inserts_product_code_before_trailing_hashtags():
    """When caption has trailing hashtags, missing product code is placed before hashtags block."""
    raw = """{
      "product": "Organizador",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": "Gancho incrivel do video!\\nConfira no link da bio!\\n\\n#achadinhos #cozinha #publi",
      "hashtags": ["#achadinhos", "#cozinha", "#publi"]
    }"""
    res = viral_studio_copy.parse_affiliate_copy_response(raw, product_code="PROD-777")
    lines = res.caption.split("\n\n")
    # Code is present
    assert "📌 Produto PROD-777" in res.caption
    # Code appears before hashtags line
    code_idx = [i for i, l in enumerate(lines) if "📌 Produto PROD-777" in l][0]
    hashtag_idx = [i for i, l in enumerate(lines) if "#achadinhos" in l][0]
    assert code_idx < hashtag_idx


def test_generate_affiliate_copy_cache_hit_empty_manual_headline_safely_falls_back(sample_brand):
    """Empty or whitespace manual_headline on cache hit falls back to headlines[0], avoiding empty string."""
    cached = AICopyData(
        product="Produto",
        headlines=["H1 Valida", "H2", "H3", "H4", "H5"],
        selected_headline="H1 Valida",
        caption="Legenda",
        hashtags=["#tag"],
    )
    item = ViralItem(
        id="item-empty-head",
        source_url="https://instagram.com/reel/123",
        ai_copy=cached,
        manual_headline="   ",  # whitespace only
        selected_headline="",   # empty
    )
    res = asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, item))
    assert res.selected_headline == "H1 Valida"
    assert len(res.headlines) <= 10


def test_generate_affiliate_copy_clamps_headlines_to_ten_when_item_has_full_list_and_manual_headline(sample_brand):
    """Manual headline addition on full 10-item headline list does not push list length to 11."""
    cached = AICopyData(
        product="Produto",
        headlines=[f"H{i}" for i in range(10)],
        selected_headline="H0",
        caption="Legenda",
        hashtags=["#tag"],
    )
    item = ViralItem(
        id="item-full-list",
        source_url="https://instagram.com/reel/123",
        ai_copy=cached,
        manual_headline="Nova Headline Manual Extrema",
    )
    res = asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, item))
    assert len(res.headlines) == 10
    assert res.selected_headline == "Nova Headline Manual Extrema"
    assert res.headlines[0] == "Nova Headline Manual Extrema"


def test_build_affiliate_copy_prompt_with_video_context(sample_brand):
    """Prompt cleanly incorporates transcript, caption, title, and keyframe references."""
    from clippyme.domain.viral_studio_context import VideoContext

    ctx = VideoContext(
        keyframes=[b"f1", b"f2", b"f3"],
        transcript="Este mini selador esquenta em 3 segundos",
        original_caption="Olha que prático esse achadinho! #cozinha",
        title="Mini Selador Portátil",
        tags=["#cozinha", "#dicas"],
        scenes_count=3,
        has_audio=True,
    )

    prompt = viral_studio_copy.build_affiliate_copy_prompt(
        brand=sample_brand,
        product_code="SEL-10",
        video_context=ctx,
    )

    assert "--- CONTEXTO EXTRAÍDO DO VÍDEO ---" in prompt
    assert "Este mini selador esquenta em 3 segundos" in prompt
    assert "Olha que prático esse achadinho!" in prompt
    assert "Mini Selador Portátil" in prompt
    assert "#cozinha, #dicas" in prompt
    assert "3 frames visuais" in prompt


def test_generate_affiliate_copy_multimodal_frames_and_context_summary(sample_brand, sample_item):
    """generate_affiliate_copy extracts context, passes multimodal payload, and saves ai_context_summary."""
    from clippyme.domain.viral_studio_context import VideoContext

    ctx = VideoContext(
        keyframes=[b"jpeg_frame_bytes_1", b"jpeg_frame_bytes_2"],
        transcript="Mini aspirador sem fio potente",
        original_caption="Melhor aspirador! #limpeza",
        title="Mini Aspirador",
        tags=["#limpeza"],
        scenes_count=2,
        has_audio=True,
        duration=10.0,
    )

    mock_resp = MagicMock()
    mock_resp.text = """{
      "product": "Mini Aspirador Sem Fio",
      "product_description": "Aspirador potente e compacto",
      "headlines": ["Limpe seu carro em minutos! 😱", "H2", "H3", "H4", "H5"],
      "selected_headline": "Limpe seu carro em minutos! 😱",
      "caption": "Limpe tudo com facilidade!\\n📌 Produto PROD-99\\nConfira na bio!\\n#achadinhos #limpeza",
      "hashtags": ["#achadinhos", "#limpeza"]
    }"""

    mock_models = AsyncMock()
    mock_models.generate_content.return_value = mock_resp
    mock_client = MagicMock()
    mock_client.aio.models = mock_models

    with patch("google.genai.Client", return_value=mock_client), \
         patch("clippyme.domain.viral_studio_store.update_item"):

        copy_res = asyncio.run(viral_studio_copy.generate_affiliate_copy(
            brand=sample_brand,
            item=sample_item,
            api_key="test-key",
            video_context=ctx,
        ))

        assert copy_res.product == "Mini Aspirador Sem Fio"
        assert sample_item.ai_context_summary is not None
        assert sample_item.ai_context_summary["scenes_count"] == 2
        assert sample_item.ai_context_summary["keyframes_count"] == 2
        assert sample_item.ai_context_summary["has_audio"] is True
        assert mock_models.generate_content.called
        call_kwargs = mock_models.generate_content.call_args[1]
        assert "contents" in call_kwargs
        # Multimodal payload is a list with frames and prompt
        assert isinstance(call_kwargs["contents"], list)
        assert len(call_kwargs["contents"]) >= 2


def test_generate_affiliate_copy_captures_llm_telemetry(sample_brand, sample_item):
    """generate_affiliate_copy captures latency, token counts, cost estimate, and raw response in ai_telemetry."""
    mock_resp = MagicMock()
    mock_resp.text = """{
      "product": "Mini Selador",
      "product_description": "Selador térmico prático",
      "headlines": ["H1", "H2", "H3", "H4", "H5"],
      "selected_headline": "H1",
      "caption": "Legenda completa",
      "hashtags": ["#achadinhos"]
    }"""
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 500
    mock_usage.candidates_token_count = 150
    mock_usage.total_token_count = 650
    mock_resp.usage_metadata = mock_usage

    mock_models = AsyncMock()
    mock_models.generate_content.return_value = mock_resp
    mock_client = MagicMock()
    mock_client.aio.models = mock_models

    item_dict = {
        "id": "item-telemetry-01",
        "source_url": "https://instagram.com/reel/123",
        "product_code": "TEL-01",
    }

    with patch("google.genai.Client", return_value=mock_client), \
         patch("clippyme.domain.viral_studio_store.update_item") as mock_update:

        copy_res = asyncio.run(viral_studio_copy.generate_affiliate_copy(
            brand=sample_brand,
            item=item_dict,
            api_key="test-key",
            model="gemini-2.5-flash",
        ))

        assert copy_res.product == "Mini Selador"
        assert "ai_telemetry" in item_dict
        telemetry = item_dict["ai_telemetry"]
        assert telemetry["model"] == "gemini-2.5-flash"
        assert telemetry["prompt_tokens"] == 500
        assert telemetry["candidate_tokens"] == 150
        assert telemetry["total_tokens"] == 650
        assert telemetry["latency_ms"] >= 0
        assert telemetry["estimated_cost_usd"] > 0
        assert "Mini Selador" in telemetry["raw_response"]
        assert "Você é um especialista" in telemetry["prompt"]
        assert mock_update.called
        update_args = mock_update.call_args[0][1]
        assert "ai_telemetry" in update_args
        assert update_args["ai_telemetry"]["total_tokens"] == 650


# ============================================================================
# Model Selection & Provider Architecture Tests
# ============================================================================

def test_parse_model_identifier():
    assert viral_studio_copy.parse_model_identifier(None) == ("gemini", "")
    assert viral_studio_copy.parse_model_identifier("") == ("gemini", "")
    assert viral_studio_copy.parse_model_identifier("gemini:gemini-3.5-flash") == ("gemini", "gemini-3.5-flash")
    assert viral_studio_copy.parse_model_identifier("gemini:gemini-3.5-flash-lite") == ("gemini", "gemini-3.5-flash-lite")
    assert viral_studio_copy.parse_model_identifier("gemini:gemini-3.6-flash") == ("gemini", "gemini-3.6-flash")
    assert viral_studio_copy.parse_model_identifier("gemini:gemini-3.1-pro-preview") == ("gemini", "gemini-3.1-pro-preview")
    assert viral_studio_copy.parse_model_identifier("ollama:llama3.2") == ("ollama", "llama3.2")
    assert viral_studio_copy.parse_model_identifier("ollama:qwen2.5") == ("ollama", "qwen2.5")
    assert viral_studio_copy.parse_model_identifier("llama3.2") == ("ollama", "llama3.2")
    assert viral_studio_copy.parse_model_identifier("qwen2.5") == ("ollama", "qwen2.5")
    assert viral_studio_copy.parse_model_identifier("google/gemma-4-12b-qat") == ("lmstudio", "google/gemma-4-12b-qat")
    assert viral_studio_copy.parse_model_identifier("prism-ml/bonsai-27b") == ("lmstudio", "prism-ml/bonsai-27b")
    assert viral_studio_copy.parse_model_identifier("lmstudio:google/gemma-4-12b-qat") == ("lmstudio", "google/gemma-4-12b-qat")
    assert viral_studio_copy.parse_model_identifier("gemini-3.5-flash") == ("gemini", "gemini-3.5-flash")


def test_ollama_provider_success():
    provider = viral_studio_copy.OllamaProvider(base_url="http://localhost:11434")
    fake_json_resp = {
        "response": json.dumps({
            "product": "Mini Selador Ollama",
            "product_description": "Selador térmico portátil",
            "headlines": ["Headline 1", "Headline 2", "Headline 3", "Headline 4", "Headline 5"],
            "selected_headline": "Headline 1",
            "caption": "Legenda gerada por Ollama",
            "hashtags": ["#ollama", "#achadinhos"],
        }),
        "total_duration": 2500000000,  # 2.5s -> 2500ms
        "prompt_eval_count": 120,
        "eval_count": 85,
    }

    with patch.object(provider, "_sync_generate", return_value=fake_json_resp):
        raw_text, telemetry = asyncio.run(provider.generate_copy("prompt text", "llama3.2"))
        assert "Mini Selador Ollama" in raw_text
        assert telemetry["provider"] == "ollama"
        assert telemetry["model"] == "ollama:llama3.2"
        assert telemetry["prompt_tokens"] == 120
        assert telemetry["candidate_tokens"] == 85
        assert telemetry["total_tokens"] == 205
        assert telemetry["latency_ms"] == 2500
        assert telemetry["cost_usd"] == 0.0


def test_ollama_provider_connection_error_raises_clippyme_error():
    import urllib.error
    provider = viral_studio_copy.OllamaProvider(base_url="http://localhost:11434")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        with pytest.raises(ClippyMeError, match="Cannot connect to Ollama"):
            asyncio.run(provider.generate_copy("prompt text", "llama3.2"))


def test_ollama_provider_empty_response_raises_clippyme_error():
    provider = viral_studio_copy.OllamaProvider(base_url="http://localhost:11434")
    with patch.object(provider, "_sync_generate", return_value={"response": ""}):
        with pytest.raises(ClippyMeError, match="Ollama returned empty response"):
            asyncio.run(provider.generate_copy("prompt text", "llama3.2"))


def test_generate_affiliate_copy_with_ollama_provider(sample_brand, sample_item):
    fake_json_resp = {
        "response": json.dumps({
            "product": "Suporte Articulado Local",
            "product_description": "Suporte articulado para monitor",
            "headlines": [
                "Melhore sua postura no home office!",
                "Organize sua mesa agora!",
                "Esse suporte vai transformar seu setup!",
                "Prático e super resistente!",
                "Achadinho perfeito para o escritório!",
            ],
            "selected_headline": "Melhore sua postura no home office!",
            "caption": "Melhore sua postura com esse suporte incrível!\\n📌 Produto PROD-99\\nConfira no link da bio!\\n#homeoffice #dicas",
            "hashtags": ["#homeoffice", "#dicas", "#achadinhos"],
        }),
        "total_duration": 1800000000,
        "prompt_eval_count": 150,
        "eval_count": 90,
    }

    item_dict = {
        "id": "item-ollama-01",
        "source_url": "https://instagram.com/reel/123",
        "product_code": "PROD-99",
        "model": "ollama:llama3.2",
    }

    with patch.object(viral_studio_copy.OllamaProvider, "_sync_generate", return_value=fake_json_resp), \
         patch("clippyme.domain.viral_studio_store.update_item") as mock_update:

        copy_res = asyncio.run(viral_studio_copy.generate_affiliate_copy(
            brand=sample_brand,
            item=item_dict,
        ))

        assert copy_res.product == "Suporte Articulado Local"
        assert copy_res.selected_headline == "Melhore sua postura no home office!"
        assert "PROD-99" in copy_res.caption
        assert item_dict["ai_telemetry"]["provider"] == "ollama"
        assert item_dict["ai_telemetry"]["model"] == "ollama:llama3.2"
        assert item_dict["ai_telemetry"]["cost_usd"] == 0.0
        assert mock_update.called


def test_generate_affiliate_copy_with_gemini_prefix(sample_brand):
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "product": "Mini Processador",
        "product_description": "Processador manual de alimentos",
        "headlines": ["H1", "H2", "H3", "H4", "H5"],
        "selected_headline": "H1",
        "caption": "Legenda com link",
        "hashtags": ["#cozinha"],
    })
    mock_resp.usage_metadata = MagicMock()
    mock_resp.usage_metadata.prompt_token_count = 100
    mock_resp.usage_metadata.candidates_token_count = 50
    mock_resp.usage_metadata.total_token_count = 150

    mock_models = AsyncMock()
    mock_models.generate_content.return_value = mock_resp
    mock_client = MagicMock()
    mock_client.aio.models = mock_models

    item_dict = {
        "id": "item-gemini-prefix",
        "source_url": "https://instagram.com/reel/456",
    }

    with patch("google.genai.Client", return_value=mock_client):
        copy_res = asyncio.run(viral_studio_copy.generate_affiliate_copy(
            brand=sample_brand,
            item=item_dict,
            api_key="test-key",
            model="gemini:gemini-3.6-flash",
        ))
        assert copy_res.product == "Mini Processador"
        assert item_dict["ai_telemetry"]["model"] == "gemini-3.6-flash"
        mock_models.generate_content.assert_called_once()
        call_kwargs = mock_models.generate_content.call_args[1]
        assert call_kwargs["model"] == "gemini-3.6-flash"


def test_lm_studio_provider_success():
    provider = viral_studio_copy.LMStudioProvider(base_url="http://localhost:1234")
    fake_json_resp = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "product": "Mini Selador LM Studio",
                        "product_description": "Selador térmico portátil",
                        "headlines": ["Headline 1", "Headline 2", "Headline 3", "Headline 4", "Headline 5"],
                        "selected_headline": "Headline 1",
                        "caption": "Legenda gerada por LM Studio",
                        "hashtags": ["#lmstudio", "#achadinhos"],
                    }),
                }
            }
        ],
        "usage": {
            "prompt_tokens": 140,
            "completion_tokens": 95,
            "total_tokens": 235,
        },
    }

    with patch.object(provider, "_sync_generate", return_value=fake_json_resp):
        raw_text, telemetry = asyncio.run(provider.generate_copy("prompt text", "qwen2.5-7b"))
        assert "Mini Selador LM Studio" in raw_text
        assert telemetry["provider"] == "lm_studio"
        assert telemetry["model"] == "lmstudio:qwen2.5-7b"
        assert telemetry["prompt_tokens"] == 140
        assert telemetry["candidate_tokens"] == 95
        assert telemetry["total_tokens"] == 235
        assert telemetry["cost_usd"] == 0.0


def test_lm_studio_provider_connection_error_raises_clippyme_error():
    import urllib.error
    provider = viral_studio_copy.LMStudioProvider(base_url="http://localhost:1234")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        with pytest.raises(ClippyMeError, match="Cannot connect to LM Studio"):
            asyncio.run(provider.generate_copy("prompt text", "qwen2.5-7b"))


def test_lm_studio_provider_empty_response_raises_clippyme_error():
    provider = viral_studio_copy.LMStudioProvider(base_url="http://localhost:1234")
    with patch.object(provider, "_sync_generate", return_value={"choices": [{"message": {"content": ""}}]}):
        with pytest.raises(ClippyMeError, match="LM Studio returned empty response"):
            asyncio.run(provider.generate_copy("prompt text", "qwen2.5-7b"))


def test_generate_affiliate_copy_with_lmstudio_provider(sample_brand, sample_item):
    fake_json_resp = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "product": "Suporte LM Studio Local",
                        "product_description": "Suporte articulado para monitor",
                        "headlines": [
                            "Melhore sua postura no home office!",
                            "Organize sua mesa agora!",
                            "Esse suporte vai transformar seu setup!",
                            "Prático e super resistente!",
                            "Achadinho perfeito para o escritório!",
                        ],
                        "selected_headline": "Melhore sua postura no home office!",
                        "caption": "Melhore sua postura com esse suporte incrível!\\n📌 Produto PROD-99\\nConfira no link da bio!\\n#homeoffice #dicas",
                        "hashtags": ["#homeoffice", "#dicas", "#achadinhos"],
                    }),
                }
            }
        ],
        "usage": {
            "prompt_tokens": 160,
            "completion_tokens": 100,
            "total_tokens": 260,
        },
    }

    item_dict = {
        "id": "item-lmstudio-01",
        "source_url": "https://instagram.com/reel/123",
        "product_code": "PROD-99",
        "model": "lmstudio:qwen2.5-7b",
    }

    with patch.object(viral_studio_copy.LMStudioProvider, "_sync_generate", return_value=fake_json_resp), \
         patch("clippyme.domain.viral_studio_store.update_item") as mock_update:

        copy_res = asyncio.run(viral_studio_copy.generate_affiliate_copy(
            brand=sample_brand,
            item=item_dict,
        ))

        assert copy_res.product == "Suporte LM Studio Local"
        assert copy_res.selected_headline == "Melhore sua postura no home office!"
        assert "PROD-99" in copy_res.caption
        assert item_dict["ai_telemetry"]["provider"] == "lm_studio"
        assert item_dict["ai_telemetry"]["model"] == "lmstudio:qwen2.5-7b"
        assert item_dict["ai_telemetry"]["cost_usd"] == 0.0
        assert mock_update.called


def test_parse_model_identifier_lmstudio_and_local():
    assert viral_studio_copy.parse_model_identifier("lmstudio:qwen2.5-7b") == ("lmstudio", "qwen2.5-7b")
    assert viral_studio_copy.parse_model_identifier("lm_studio:model-x") == ("lmstudio", "model-x")
    assert viral_studio_copy.parse_model_identifier("local:my-model") == ("lmstudio", "my-model")
    assert viral_studio_copy.parse_model_identifier("lmstudio/qwen2.5-7b") == ("lmstudio", "qwen2.5-7b")


def test_lm_studio_provider_candidate_fallback(monkeypatch):
    import urllib.error
    monkeypatch.delenv("LM_STUDIO_BASE_URL", raising=False)
    provider = viral_studio_copy.LMStudioProvider()
    
    # Simulate first candidate failing with URLError, second returning success JSON
    class FakeResponse:
        def getcode(self):
            return 200
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": json.dumps({"headlines": ["H1"], "caption": "Cap"})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            }).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    call_count = 0
    def fake_urlopen(req, timeout=120):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise urllib.error.URLError("Connection refused on candidate 1")
        return FakeResponse()

    with patch("clippyme.domain.viral_studio_copy.load_persistent_config", return_value={}), \
         patch("urllib.request.urlopen", side_effect=fake_urlopen):
        raw_text, telemetry = asyncio.run(provider.generate_copy("prompt", "qwen2.5"))
        assert call_count == 2
        assert "H1" in raw_text
        assert telemetry["provider"] == "lm_studio"


def test_ollama_provider_candidate_fallback(monkeypatch):
    import urllib.error
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    provider = viral_studio_copy.OllamaProvider()

    class FakeResponse:
        def getcode(self):
            return 200
        def read(self):
            return json.dumps({
                "response": "{\"headlines\": [\"Ollama H1\"], \"caption\": \"Cap\"}",
                "prompt_eval_count": 10,
                "eval_count": 10,
            }).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    call_count = 0
    def fake_urlopen(req, timeout=120):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise urllib.error.URLError("Connection refused on candidate 1")
        return FakeResponse()

    with patch("clippyme.domain.viral_studio_copy.load_persistent_config", return_value={}), \
         patch("urllib.request.urlopen", side_effect=fake_urlopen):
        raw_text, telemetry = asyncio.run(provider.generate_copy("prompt", "llama3.2"))
        assert call_count == 2
        assert "Ollama H1" in raw_text
        assert telemetry["provider"] == "ollama"


def test_generate_affiliate_copy_model_resolution_precedence(sample_brand, sample_item):
    """Resolution order: explicit model > DEFAULT_AI_MODEL > GEMINI_MODEL > gemini-3.5-flash."""
    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "product": "P",
        "headlines": ["H1", "H2", "H3", "H4", "H5"],
        "selected_headline": "H1",
        "caption": "Cap",
        "hashtags": ["#tag"],
    })
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    # DEFAULT_AI_MODEL is used when no explicit model passed
    sample_item.model = None
    with patch("clippyme.domain.viral_studio_copy.load_persistent_config", return_value={"DEFAULT_AI_MODEL": "gemini-3.6-flash", "GEMINI_MODEL": "gemini-2.5-flash"}), \
         patch("google.genai.Client", return_value=mock_client):
        res = asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, sample_item, api_key="dummy"))
        assert res.product == "P"
        mock_client.aio.models.generate_content.assert_called_with(model="gemini-3.6-flash", contents=mock_client.aio.models.generate_content.call_args[1]["contents"])


def test_local_provider_failure_does_not_silently_fallback_to_gemini(sample_brand, sample_item):
    """When a local model is specified and LM Studio fails, raise ClippyMeError instead of falling back to Gemini."""
    sample_item.model = "lmstudio:google/gemma-4-12b-qat"
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")), \
         patch("google.genai.Client") as mock_gemini:
        with pytest.raises(ClippyMeError) as exc_info:
            asyncio.run(viral_studio_copy.generate_affiliate_copy(sample_brand, sample_item))
        assert not mock_gemini.called
def test_parse_model_identifier_tagged_and_prefixed():
    """Verify parse_model_identifier handles tags, slash models, and provider prefixes."""
    assert viral_studio_copy.parse_model_identifier("ollama:llama3.2:latest") == ("ollama", "llama3.2:latest")
    assert viral_studio_copy.parse_model_identifier("llama3.2:latest") == ("ollama", "llama3.2:latest")
    assert viral_studio_copy.parse_model_identifier("mistral:7b") == ("ollama", "mistral:7b")
    assert viral_studio_copy.parse_model_identifier("gemini:gemini-3.5-flash") == ("gemini", "gemini-3.5-flash")
    assert viral_studio_copy.parse_model_identifier("gemini-3.5-flash") == ("gemini", "gemini-3.5-flash")
    assert viral_studio_copy.parse_model_identifier("lmstudio:google/gemma-4-12b-qat") == ("lmstudio", "google/gemma-4-12b-qat")
    assert viral_studio_copy.parse_model_identifier("google/gemma-4-12b-qat") == ("lmstudio", "google/gemma-4-12b-qat")
    assert viral_studio_copy.parse_model_identifier("") == ("gemini", "")
    assert viral_studio_copy.parse_model_identifier(None) == ("gemini", "")









