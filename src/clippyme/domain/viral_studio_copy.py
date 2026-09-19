"""Commercial AI Copy Generation for Viral Content Studio (Milestone 3).

Generates high-converting affiliate marketing copy, headlines, and structured captions
in Brazilian Portuguese (PT-BR) using the Gemini API.

Key components:
- ``build_affiliate_copy_prompt``: Pure function constructing PT-BR commercial prompt.
- ``parse_affiliate_copy_response``: Pure function with multi-level JSON repair fallback chain.
- ``generate_affiliate_copy``: Async client with model fallback and item-level caching.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

from clippyme.api.viral_studio_schemas import AICopyData, Brand, ViralItem
from clippyme.domain.errors import ClippyMeError, ValidationError
from clippyme.pipeline.gemini_service import _redact_key
from clippyme.storage.config_store import load_persistent_config

logger = logging.getLogger("clippyme.viral_studio_copy")

# Clean-up regex patterns
_CODE_FENCE_OPEN = re.compile(r"^\s*```(?:json)?\s*", re.IGNORECASE)
_CODE_FENCE_CLOSE = re.compile(r"\s*```\s*$")
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")
_LONE_BACKSLASH = re.compile(r'\\(?!["\\/bfnrtu])')
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

DEFAULT_FALLBACK_HEADLINES = [
    "Quem tem pouco espaço precisa ver isso! 😱",
    "Olha esse achadinho incrível para a sua casa!",
    "Esse produto pode transformar a sua rotina!",
    "Muito prático e útil, você vai amar isso!",
    "O achadinho perfeito que você não sabia que precisava!",
]

DEFAULT_FALLBACK_HASHTAGS = [
    "#achadinhos",
    "#shopee",
    "#dicas",
    "#casa",
    "#organizacao",
    "#utilidades",
    "#publi",
]

DEFAULT_MODELS_FALLBACK_CHAIN = [
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]


def _extract_field(obj: Any, field_name: str, default: Any = None) -> Any:
    """Helper to extract field from either Pydantic model or dict."""
    if isinstance(obj, dict):
        return obj.get(field_name, default)
    return getattr(obj, field_name, default)


def build_affiliate_copy_prompt(
    brand: Union[Brand, Dict[str, Any]],
    product_code: Optional[str] = None,
    product_url: Optional[str] = None,
    manual_instructions: Optional[str] = None,
) -> str:
    """Build the prompt for Gemini affiliate copy generation. Pure function.

    Generates instructions in Brazilian Portuguese (PT-BR) tailored for
    high-converting affiliate videos (Instagram Reels / TikTok / YouTube Shorts).
    """
    brand_name = _extract_field(brand, "name", "Achadinhos")
    brand_handle = _extract_field(brand, "handle", "@achadinhos")
    default_cta = _extract_field(brand, "default_cta", "Confira os achadinhos no link da bio!")

    product_code_str = str(product_code).strip() if product_code else ""
    product_url_str = str(product_url).strip() if product_url else ""
    instructions_str = str(manual_instructions).strip() if manual_instructions else ""

    code_instruction = ""
    if product_code_str:
        code_instruction = (
            f"- Código do produto: {product_code_str}. É OBRIGATÓRIO incluir na legenda de forma clara, "
            f"exatamente como '📌 Produto {product_code_str}' (ou 'Código: {product_code_str}'). "
            "NUNCA invente outros códigos, cupons ou descontos fictícios.\n"
        )

    url_instruction = ""
    if product_url_str:
        url_instruction = f"- Link / URL de referência do produto: {product_url_str}\n"

    user_instructions = ""
    if instructions_str:
        user_instructions = f"- Instruções adicionais do usuário: \"{instructions_str}\"\n"

    prompt = (
        "Você é um especialista em marketing de afiliados brasileiro e copywriter de vídeos virais "
        "para Instagram Reels, TikTok e YouTube Shorts (formato 'Achadinhos').\n"
        "Sua missão é analisar o produto demonstrado e produzir textos comerciais de alta conversão "
        "em Português Brasileiro (PT-BR).\n\n"
        "--- CONTEXTO DA MARCA ---\n"
        f"- Nome da marca: {brand_name}\n"
        f"- Perfil / Handle: {brand_handle}\n"
        f"- CTA padrão da marca: {default_cta}\n"
        f"{code_instruction}"
        f"{url_instruction}"
        f"{user_instructions}\n"
        "--- REGRAS DE GERAÇÃO ---\n"
        "1. HEADLINES:\n"
        "   - Crie exatamente 5 opções de headlines curtas e magnéticas para sobreposição no vídeo.\n"
        "   - Devem despertar alta curiosidade e destacar o principal benefício demonstrado.\n"
        "   - Use português brasileiro natural, com pontuação expressiva ou emojis adequados.\n"
        "   - Evite clichês vazios; foque no problema que o produto resolve.\n"
        "   - Escolha a melhor opção e coloque em 'selected_headline'.\n"
        "2. LEGENDA ESTRUTURADA (CAPTION):\n"
        "   - Gancho inicial impactante na primeira linha.\n"
        "   - Breve descrição do produto e facilidade de uso.\n"
        "   - Benefício prático demonstrado.\n"
        f"   - O código do produto ({product_code_str or 'se informado'}).\n"
        f"   - Chamada para ação (CTA), utilizando ou adaptando: '{default_cta}'.\n"
        "   - 4 a 7 hashtags altamente relevantes (#achadinhos, nicho do produto, #publi).\n"
        "3. INTEGRIDADE COMERCIAL:\n"
        "   - NUNCA invente funcionalidades milagrosas que não existem no produto.\n"
        "   - NUNCA invente preços, porcentagens de desconto ou códigos promocionais não fornecidos.\n"
        "   - NUNCA use promessas enganosas.\n\n"
        "--- FORMATO DE RESPOSTA ---\n"
        "Responda EXCLUSIVAMENTE em JSON válido, sem texto antes ou depois, seguindo esta estrutura:\n"
        "{\n"
        '  "product": "Nome conciso do produto identificado",\n'
        '  "product_description": "Breve descrição do produto e sua utilidade",\n'
        '  "headlines": [\n'
        '    "Opção 1 de headline curta e chamativa",\n'
        '    "Opção 2 ...",\n'
        '    "Opção 3 ...",\n'
        '    "Opção 4 ...",\n'
        '    "Opção 5 ..."\n'
        "  ],\n"
        '  "selected_headline": "A melhor opção escolhida entre as 5 acima",\n'
        '  "caption": "Legenda completa estruturada com gancho, descrição, código, CTA e hashtags",\n'
        '  "hashtags": ["#achadinhos", "#dicas", "#utilidades", "#publi"]\n'
        "}\n"
    )
    return prompt


def _clean_json_str(raw: str) -> str:
    """Apply deterministic string cleaning to fix common LLM JSON syntax errors."""
    cleaned = (
        raw.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    cleaned = _TRAILING_COMMA.sub(r"\1", cleaned)
    cleaned = _LONE_BACKSLASH.sub(r"\\\\", cleaned)
    cleaned = _CONTROL_CHARS.sub("", cleaned)
    return cleaned


def parse_affiliate_copy_response(
    raw_text: str,
    default_cta: str = "Confira os achadinhos no link da bio!",
    product_code: Optional[str] = None,
) -> AICopyData:
    """Parse Gemini raw output into a validated AICopyData model. Pure function.

    Uses a 5-level repair chain:
    1. Strip markdown fences and whitespace.
    2. Substring slice between first '{' and last '}'.
    3. Strict json.loads.
    4. Deterministic string repair (_clean_json_str).
    5. json_repair library (if available).
    6. Safe graceful fallback construction.
    """
    if not raw_text or not raw_text.strip():
        return _build_fallback_copy_data(default_cta, product_code)

    text = raw_text.strip()
    # Strip markdown fences
    text = _CODE_FENCE_OPEN.sub("", text)
    text = _CODE_FENCE_CLOSE.sub("", text).strip()

    # Extract JSON between first '{' and last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        json_candidate = text[start : end + 1]
    else:
        json_candidate = text

    parsed_obj: Optional[Dict[str, Any]] = None

    # Level 1: Strict JSON parse
    try:
        data = json.loads(json_candidate)
        if isinstance(data, dict):
            parsed_obj = data
    except (json.JSONDecodeError, ValueError):
        pass

    # Level 2: Deterministic clean
    if parsed_obj is None:
        try:
            cleaned = _clean_json_str(json_candidate)
            data = json.loads(cleaned)
            if isinstance(data, dict):
                parsed_obj = data
        except (json.JSONDecodeError, ValueError):
            pass

    # Level 3: json_repair library
    if parsed_obj is None:
        try:
            from json_repair import repair_json  # type: ignore

            repaired = repair_json(json_candidate)
            data = json.loads(repaired)
            if isinstance(data, dict):
                parsed_obj = data
        except Exception:
            pass

    # Level 4: Regex-based field extraction as final recovery attempt
    if parsed_obj is None:
        parsed_obj = _regex_extract_copy_fields(text)

    # If all parsing attempts fail, return fallback
    if not parsed_obj:
        return _build_fallback_copy_data(default_cta, product_code)

    # Validate and normalize extracted fields
    return _normalize_parsed_dict(parsed_obj, default_cta, product_code)


def _regex_extract_copy_fields(text: str) -> Optional[Dict[str, Any]]:
    """Attempt heuristic regex extraction of fields from malformed JSON."""
    result: Dict[str, Any] = {}
    prod_m = re.search(r'"product"\s*:\s*"([^"]+)"', text)
    if prod_m:
        result["product"] = prod_m.group(1)

    desc_m = re.search(r'"product_description"\s*:\s*"([^"]+)"', text)
    if desc_m:
        result["product_description"] = desc_m.group(1)

    sel_h_m = re.search(r'"selected_headline"\s*:\s*"([^"]+)"', text)
    if sel_h_m:
        result["selected_headline"] = sel_h_m.group(1)

    caption_m = re.search(r'"caption"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if caption_m:
        result["caption"] = caption_m.group(1).replace(r"\n", "\n")

    headlines_m = re.search(r'"headlines"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if headlines_m:
        raw_items = re.findall(r'"([^"]+)"', headlines_m.group(1))
        if raw_items:
            result["headlines"] = raw_items

    hashtags_m = re.search(r'"hashtags"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if hashtags_m:
        raw_tags = re.findall(r'"([^"]+)"', hashtags_m.group(1))
        if raw_tags:
            result["hashtags"] = raw_tags

    return result if result.get("headlines") or result.get("caption") else None


def _normalize_parsed_dict(
    data: Dict[str, Any],
    default_cta: str,
    product_code: Optional[str] = None,
) -> AICopyData:
    """Ensure all required AICopyData fields are clean, non-empty, and compliant."""
    product = str(data.get("product") or "Produto em Destaque").strip()[:200]
    product_desc = str(data.get("product_description") or "").strip()[:1000]

    # Normalize headlines
    raw_headlines = data.get("headlines")
    headlines: List[str] = []
    if isinstance(raw_headlines, list):
        for h in raw_headlines:
            if isinstance(h, str) and h.strip():
                headlines.append(h.strip()[:300])

    if not headlines:
        headlines = list(DEFAULT_FALLBACK_HEADLINES)
    elif len(headlines) < 5:
        # Pad up to 5 with diverse fallback headlines
        for fallback_h in DEFAULT_FALLBACK_HEADLINES:
            if fallback_h not in headlines:
                headlines.append(fallback_h)
            if len(headlines) >= 5:
                break

    headlines = headlines[:10]

    # Selected headline
    selected_headline = str(data.get("selected_headline") or "").strip()
    if not selected_headline or selected_headline not in headlines:
        selected_headline = headlines[0]
    selected_headline = selected_headline[:300]

    # Hashtags
    raw_hashtags = data.get("hashtags")
    hashtags: List[str] = []
    if isinstance(raw_hashtags, list):
        for tag in raw_hashtags:
            if isinstance(tag, str):
                cleaned_tag = tag.strip().replace(" ", "")
                if cleaned_tag:
                    if not cleaned_tag.startswith("#"):
                        cleaned_tag = f"#{cleaned_tag}"
                    if cleaned_tag not in hashtags:
                        hashtags.append(cleaned_tag)
    if not hashtags:
        hashtags = list(DEFAULT_FALLBACK_HASHTAGS)

    # Caption
    caption = str(data.get("caption") or "").strip()
    if not caption:
        # Assemble structured caption
        parts = [selected_headline]
        if product_desc:
            parts.append(product_desc)
        if product_code:
            parts.append(f"📌 Produto {product_code}")
        parts.append(default_cta)
        parts.append(" ".join(hashtags))
        caption = "\n\n".join(parts)
    else:
        # Guarantee product code is in caption if provided
        if product_code and str(product_code) not in caption:
            caption = f"{caption}\n📌 Produto {product_code}"

    caption = caption[:2200]

    return AICopyData(
        product=product,
        product_description=product_desc,
        headlines=headlines,
        selected_headline=selected_headline,
        caption=caption,
        hashtags=hashtags,
    )


def _build_fallback_copy_data(
    default_cta: str,
    product_code: Optional[str] = None,
) -> AICopyData:
    """Generate safe fallback AICopyData when model output is completely missing."""
    headlines = list(DEFAULT_FALLBACK_HEADLINES)
    selected_headline = headlines[0]
    hashtags = list(DEFAULT_FALLBACK_HASHTAGS)

    parts = [
        selected_headline,
        "Esse achadinho vai transformar o seu espaço e facilitar muito o seu dia a dia!",
    ]
    if product_code:
        parts.append(f"📌 Produto {product_code}")
    parts.append(default_cta)
    parts.append(" ".join(hashtags))
    caption = "\n\n".join(parts)

    return AICopyData(
        product="Produto em Destaque",
        product_description="Achadinho incrível com alta utilidade para sua rotina.",
        headlines=headlines,
        selected_headline=selected_headline,
        caption=caption,
        hashtags=hashtags,
    )


async def generate_affiliate_copy(
    brand: Union[Brand, Dict[str, Any]],
    item: Union[ViralItem, Dict[str, Any]],
    video_path: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> AICopyData:
    """Generate affiliate copy for a viral item with caching and model fallback.

    - Checks item-level cache first: returns cached copy immediately if present.
    - Resolves Gemini API key and fallback model ladder.
    - Executes async content generation.
    - Parses and validates response with multi-level repair.
    - Caches copy on item and persists to viral_studio_store if item has an ID.
    """
    # 1. Caching check: bypass Gemini if item already has ai_copy
    existing_copy = _extract_field(item, "ai_copy")
    if existing_copy is not None:
        if isinstance(existing_copy, AICopyData):
            logger.info("generate_affiliate_copy: Returning cached AICopyData for item")
            return existing_copy
        elif isinstance(existing_copy, dict):
            try:
                copy_obj = AICopyData.model_validate(existing_copy)
                logger.info("generate_affiliate_copy: Returning cached AICopyData from dict")
                return copy_obj
            except Exception:
                pass

    # 2. Key resolution
    resolved_api_key = (
        api_key
        or load_persistent_config().get("GEMINI_API_KEY")
        or ""
    )
    if not resolved_api_key:
        raise ValidationError("Gemini API key is not configured")

    # 3. Model ladder resolution
    configured_model = (
        model
        or load_persistent_config().get("GEMINI_MODEL")
        or "gemini-3.5-flash"
    )
    candidate_models = [configured_model]
    for m in DEFAULT_MODELS_FALLBACK_CHAIN:
        if m not in candidate_models:
            candidate_models.append(m)

    # 4. Build prompt
    product_code = _extract_field(item, "product_code")
    product_url = _extract_field(item, "product_url")
    instructions = (
        _extract_field(item, "additional_instructions")
        or _extract_field(item, "manual_instructions")
    )
    default_cta = _extract_field(brand, "default_cta", "Confira os achadinhos no link da bio!")

    prompt = build_affiliate_copy_prompt(
        brand=brand,
        product_code=product_code,
        product_url=product_url,
        manual_instructions=instructions,
    )

    # 5. Call Gemini API across fallback ladder
    from google import genai

    client = genai.Client(api_key=resolved_api_key)
    raw_response_text: Optional[str] = None
    last_error: Optional[Exception] = None

    for candidate_model in candidate_models:
        try:
            logger.info("generate_affiliate_copy: Attempting model %s", candidate_model)
            # Check for async client capability
            if hasattr(client, "aio") and hasattr(client.aio, "models"):
                resp = await client.aio.models.generate_content(
                    model=candidate_model,
                    contents=prompt,
                )
            else:
                resp = await asyncio.to_thread(
                    client.models.generate_content,
                    model=candidate_model,
                    contents=prompt,
                )

            raw_response_text = getattr(resp, "text", None) or ""
            if raw_response_text.strip():
                logger.info("generate_affiliate_copy: Success with model %s", candidate_model)
                break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "generate_affiliate_copy: Model %s failed (%s); trying fallback",
                candidate_model,
                _redact_key(str(exc)),
            )

    if raw_response_text is None or not raw_response_text.strip():
        if last_error is not None:
            raise ClippyMeError(
                f"Gemini affiliate copy generation failed: {_redact_key(str(last_error))}"
            )
        raise ClippyMeError("Gemini returned empty response for affiliate copy")

    # 6. Parse and validate response
    copy_data = parse_affiliate_copy_response(
        raw_text=raw_response_text,
        default_cta=default_cta,
        product_code=product_code,
    )

    # Honor manual headline override if present on item
    manual_headline = _extract_field(item, "manual_headline")
    if manual_headline and str(manual_headline).strip():
        clean_manual = str(manual_headline).strip()
        copy_data.selected_headline = clean_manual
        if clean_manual not in copy_data.headlines:
            copy_data.headlines.insert(0, clean_manual)

    # 7. Cache results on item
    if isinstance(item, dict):
        item["ai_copy"] = copy_data.model_dump()
        if not item.get("selected_headline"):
            item["selected_headline"] = copy_data.selected_headline
        if not item.get("caption"):
            item["caption"] = copy_data.caption
    else:
        try:
            item.ai_copy = copy_data
            if not getattr(item, "selected_headline", None):
                item.selected_headline = copy_data.selected_headline
            if not getattr(item, "caption", None):
                item.caption = copy_data.caption
        except Exception as e:
            logger.debug("Could not assign ai_copy directly to item object: %s", e)

    # 8. Persist to store if item has an ID
    item_id = _extract_field(item, "id") or _extract_field(item, "item_id")
    if item_id:
        try:
            from clippyme.domain import viral_studio_store

            viral_studio_store.update_item(
                item_id,
                {
                    "ai_copy": copy_data.model_dump(),
                    "selected_headline": copy_data.selected_headline,
                    "caption": copy_data.caption,
                },
            )
        except Exception as exc:
            logger.debug("Could not persist ai_copy to viral_studio_store: %s", exc)

    return copy_data


__all__ = [
    "build_affiliate_copy_prompt",
    "parse_affiliate_copy_response",
    "generate_affiliate_copy",
]
