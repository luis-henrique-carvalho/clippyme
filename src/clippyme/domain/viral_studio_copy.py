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
import time
from typing import Any, Dict, List, Optional, Union

from clippyme.api.viral_studio_schemas import AICopyData, Brand, ViralItem
from clippyme.domain.errors import ClippyMeError, ValidationError
from clippyme.pipeline.gemini_service import _redact_key
from clippyme.storage.config_store import load_persistent_config

logger = logging.getLogger("clippyme.viral_studio_copy")

# Per-model pricing ($ per 1M tokens)
MODEL_PRICING = {
    "gemini-3.6-flash": {"input": 1.50, "output": 9.00},
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00},
    "gemini-3.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00},
    "gemini-3.1-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
}

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
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.1-pro-preview",
]


_KNOWN_PROVIDER_PREFIXES = ("lmstudio", "lm_studio", "local", "ollama", "gemini", "google")


def parse_model_identifier(model_str: Optional[str]) -> tuple[str, str]:
    """Parse a model identifier string (e.g. 'gemini:gemini-3.5-flash', 'lmstudio:google/gemma-4-12b-qat', 'ollama:llama3.2:latest', or un-prefixed).

    Returns a tuple of (provider, model_name). Default provider is 'gemini'.
    """
    if not model_str or not str(model_str).strip():
        return ("gemini", "")
    s = str(model_str).strip()
    if ":" in s:
        p, m = s.split(":", 1)
        p_norm = p.strip().lower()
        if p_norm in ("lmstudio", "lm_studio", "local"):
            return ("lmstudio", m.strip())
        if p_norm == "ollama":
            return ("ollama", m.strip())
        if p_norm in ("gemini", "google"):
            return ("gemini", m.strip())
        if p_norm in _KNOWN_PROVIDER_PREFIXES:
            return (p_norm, m.strip())
    s_lower = s.lower()
    if s_lower.startswith("lmstudio") or s_lower.startswith("local"):
        if s_lower.startswith("lmstudio"):
            return ("lmstudio", s[8:].lstrip(":/ "))
        return ("lmstudio", s[5:].lstrip(":/ "))
    if s_lower.startswith("gemini"):
        return ("gemini", s)
    if s_lower.startswith("ollama"):
        return ("ollama", s[6:].lstrip(":/ "))
    # If the identifier has a slash (e.g. 'google/gemma-4-12b-qat', 'prism-ml/bonsai-27b')
    # it is an LM Studio / HuggingFace formatted local model
    if "/" in s:
        return ("lmstudio", s)
    # Plain un-prefixed names like 'llama3.2', 'llama3.2:latest', 'qwen2.5', 'mistral:7b' route to ollama
    if any(s_lower.startswith(prefix) for prefix in ("llama", "qwen", "mistral", "deepseek", "phi", "gemma", "bonsai", "muse", "nemotron", "starcoder", "codellama")):
        return ("ollama", s)
    return ("gemini", s)



class BaseAIProvider:
    """Abstract base class for commercial copy AI generation providers."""

    async def generate_copy(
        self,
        prompt: str,
        model_name: str,
        *,
        contents_payload: Any = None,
        api_key: Optional[str] = None,
    ) -> tuple[str, Dict[str, Any]]:
        raise NotImplementedError


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI copy generator with automatic fallback chain."""

    async def generate_copy(
        self,
        prompt: str,
        model_name: str,
        *,
        contents_payload: Any = None,
        api_key: Optional[str] = None,
    ) -> tuple[str, Dict[str, Any]]:
        import os
        from google import genai

        resolved_api_key = (
            api_key
            or load_persistent_config().get("GEMINI_API_KEY")
            or os.environ.get("GEMINI_API_KEY", "")
            or ""
        )
        if not resolved_api_key:
            raise ValidationError("Gemini API key is not configured")

        configured_model = model_name or load_persistent_config().get("GEMINI_MODEL") or "gemini-3.5-flash"
        if configured_model.startswith("gemini:"):
            configured_model = configured_model[7:].strip()
        candidate_models = [configured_model]
        for m in DEFAULT_MODELS_FALLBACK_CHAIN:
            if m not in candidate_models:
                candidate_models.append(m)


        client = genai.Client(api_key=resolved_api_key)
        payload = contents_payload if contents_payload is not None else prompt

        raw_response_text: Optional[str] = None
        last_error: Optional[Exception] = None
        succeeded_model: Optional[str] = None
        latency_ms: int = 0
        prompt_tokens: int = 0
        candidate_tokens: int = 0
        total_tokens: int = 0

        for candidate_model in candidate_models:
            try:
                logger.info("GeminiProvider: Attempting model %s", candidate_model)
                t0 = time.monotonic()
                if hasattr(client, "aio") and hasattr(client.aio, "models"):
                    resp = await client.aio.models.generate_content(
                        model=candidate_model,
                        contents=payload,
                    )
                else:
                    resp = await asyncio.to_thread(
                        client.models.generate_content,
                        model=candidate_model,
                        contents=payload,
                    )
                latency_ms = max(1, int((time.monotonic() - t0) * 1000))

                raw_response_text = getattr(resp, "text", None) or ""
                if raw_response_text.strip():
                    succeeded_model = candidate_model
                    usage = getattr(resp, "usage_metadata", None)
                    if usage:
                        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
                        candidate_tokens = getattr(usage, "candidates_token_count", 0) or 0
                        total_tokens = getattr(usage, "total_token_count", 0) or (prompt_tokens + candidate_tokens)
                    logger.info("GeminiProvider: Success with model %s (%d ms)", candidate_model, latency_ms)
                    break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "GeminiProvider: Model %s failed (%s); trying fallback",
                    candidate_model,
                    _redact_key(str(exc)),
                )

        if raw_response_text is None or not raw_response_text.strip():
            if last_error is not None:
                raise ClippyMeError(
                    f"Gemini affiliate copy generation failed: {_redact_key(str(last_error))}"
                )
            raise ClippyMeError("Gemini returned empty response for affiliate copy")

        if not prompt_tokens and prompt:
            prompt_tokens = max(1, len(prompt) // 4)
        if not candidate_tokens and raw_response_text:
            candidate_tokens = max(1, len(raw_response_text) // 4)
        if not total_tokens:
            total_tokens = prompt_tokens + candidate_tokens

        used_model = succeeded_model or configured_model
        pricing = MODEL_PRICING.get(used_model, {"input": 0.30, "output": 2.50})
        estimated_cost_usd = round(
            (prompt_tokens * pricing["input"] + candidate_tokens * pricing["output"]) / 1_000_000, 6
        )

        telemetry_data = {
            "provider": "gemini",
            "model": used_model,
            "model_used": used_model,
            "prompt_tokens": prompt_tokens,
            "candidate_tokens": candidate_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "cost_usd": estimated_cost_usd,
            "latency_ms": latency_ms,
            "prompt": prompt,
            "raw_response": raw_response_text,
        }
        return raw_response_text, telemetry_data


class OllamaProvider(BaseAIProvider):
    """Local Ollama AI copy generator supporting /api/generate endpoint."""

    def __init__(self, base_url: Optional[str] = None):
        self._base_url = base_url

    def _get_candidate_urls(self) -> List[str]:
        import os
        if self._base_url:
            return [str(self._base_url).rstrip("/")]
        configured = os.environ.get("OLLAMA_BASE_URL") or load_persistent_config().get("OLLAMA_BASE_URL")
        if configured:
            return [str(configured).rstrip("/")]
        return [
            "http://host.docker.internal:11434",
            "http://localhost:11434",
            "http://127.0.0.1:11434",
        ]

    def _sync_generate(
        self,
        model_name: str,
        prompt: str,
        images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        import json
        import urllib.error
        import urllib.request

        req_body: Dict[str, Any] = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        if images and isinstance(images, list):
            req_body["images"] = images

        data_bytes = json.dumps(req_body).encode("utf-8")
        candidates = self._get_candidate_urls()
        last_err: Optional[Exception] = None

        for base_url in candidates:
            endpoint = f"{base_url}/api/generate"
            req = urllib.request.Request(
                endpoint,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=300) as response:
                    status_code = response.getcode()
                    resp_bytes = response.read()
                    if status_code >= 400:
                        raise ClippyMeError(
                            f"Ollama API returned HTTP {status_code}: {resp_bytes.decode('utf-8', errors='replace')}"
                        )
                    return json.loads(resp_bytes.decode("utf-8"))
            except urllib.error.HTTPError as err:
                err_body = err.read().decode("utf-8", errors="replace") if hasattr(err, "read") else str(err)
                raise ClippyMeError(f"Ollama HTTP error {err.code} ({model_name} at {base_url}): {err_body}") from err
            except urllib.error.URLError as err:
                last_err = err
                continue
            except Exception as exc:
                raise ClippyMeError(f"Ollama generation failed ({model_name} at {base_url}): {exc}") from exc

        err_msg = last_err.reason if last_err and hasattr(last_err, "reason") else (str(last_err) if last_err else "connection refused")
        raise ClippyMeError(f"Cannot connect to Ollama ({model_name} at {candidates}): {err_msg}")

    async def generate_copy(
        self,
        prompt: str,
        model_name: str,
        *,
        contents_payload: Any = None,
        api_key: Optional[str] = None,
    ) -> tuple[str, Dict[str, Any]]:
        import base64
        used_model = model_name or "llama3.2"
        if used_model.startswith("ollama:"):
            used_model = used_model[7:].strip()
        logger.info("OllamaProvider: Calling Ollama model %s", used_model)


        # Extract base64 image frames if multimodal payload is supplied
        images_b64: List[str] = []
        if isinstance(contents_payload, list):
            for part in contents_payload:
                if hasattr(part, "inline_data") and hasattr(part.inline_data, "data"):
                    b = part.inline_data.data
                    if isinstance(b, bytes):
                        images_b64.append(base64.b64encode(b).decode("utf-8"))
                elif isinstance(part, bytes):
                    images_b64.append(base64.b64encode(part).decode("utf-8"))

        t0 = time.monotonic()
        data = await asyncio.to_thread(self._sync_generate, used_model, prompt, images_b64 or None)
        elapsed_ms = max(1, int((time.monotonic() - t0) * 1000))

        raw_response = data.get("response", "")
        if not raw_response or not str(raw_response).strip():
            raise ClippyMeError(f"Ollama returned empty response for model {used_model}")

        raw_response_text = str(raw_response)
        total_duration_ns = data.get("total_duration") or 0
        latency_ms = max(1, int(total_duration_ns / 1_000_000)) if total_duration_ns else elapsed_ms

        prompt_eval_count = data.get("prompt_eval_count") or 0
        eval_count = data.get("eval_count") or 0
        prompt_tokens = prompt_eval_count or max(1, len(prompt) // 4)
        candidate_tokens = eval_count or max(1, len(raw_response_text) // 4)
        total_tokens = prompt_tokens + candidate_tokens

        telemetry_data = {
            "provider": "ollama",
            "model": f"ollama:{used_model}",
            "model_used": f"ollama:{used_model}",
            "prompt_tokens": prompt_tokens,
            "candidate_tokens": candidate_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": 0.0,
            "cost_usd": 0.0,
            "latency_ms": latency_ms,
            "prompt": prompt,
            "raw_response": raw_response_text,
        }
        return raw_response_text, telemetry_data


class LMStudioProvider(BaseAIProvider):
    """Local LM Studio AI copy generator supporting OpenAI-compatible /v1/chat/completions."""

    def __init__(self, base_url: Optional[str] = None):
        self._base_url = base_url

    def _get_candidate_urls(self) -> List[str]:
        import os
        if self._base_url:
            return [str(self._base_url).rstrip("/")]
        configured = os.environ.get("LM_STUDIO_BASE_URL") or load_persistent_config().get("LM_STUDIO_BASE_URL")
        if configured:
            return [str(configured).rstrip("/")]
        return [
            "http://host.docker.internal:1234",
            "http://localhost:1234",
            "http://127.0.0.1:1234",
        ]

    def _sync_generate(
        self,
        model_name: str,
        prompt: str,
        images: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        import json
        import urllib.error
        import urllib.request

        if images and isinstance(images, list):
            content_parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
            for img_b64 in images:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                })
            user_message: Dict[str, Any] = {"role": "user", "content": content_parts}
        else:
            user_message = {"role": "user", "content": prompt}

        req_body: Dict[str, Any] = {
            "model": model_name,
            "messages": [user_message],
            "temperature": 0.7,
        }

        data_bytes = json.dumps(req_body).encode("utf-8")
        candidates = self._get_candidate_urls()
        last_err: Optional[Exception] = None

        for base_url in candidates:
            endpoint = f"{base_url}/v1/chat/completions"
            req = urllib.request.Request(
                endpoint,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=300) as response:
                    status_code = response.getcode()
                    resp_bytes = response.read()
                    if status_code >= 400:
                        raise ClippyMeError(
                            f"LM Studio API returned HTTP {status_code}: {resp_bytes.decode('utf-8', errors='replace')}"
                        )
                    return json.loads(resp_bytes.decode("utf-8"))
            except urllib.error.HTTPError as err:
                err_body = err.read().decode("utf-8", errors="replace") if hasattr(err, "read") else str(err)
                raise ClippyMeError(f"LM Studio HTTP error {err.code} ({model_name} at {base_url}): {err_body}") from err
            except urllib.error.URLError as err:
                last_err = err
                continue
            except Exception as exc:
                raise ClippyMeError(f"LM Studio generation failed ({model_name} at {base_url}): {exc}") from exc

        err_msg = last_err.reason if last_err and hasattr(last_err, "reason") else (str(last_err) if last_err else "connection refused")
        raise ClippyMeError(f"Cannot connect to LM Studio ({model_name} at {candidates}): {err_msg}")

    async def generate_copy(
        self,
        prompt: str,
        model_name: str,
        *,
        contents_payload: Any = None,
        api_key: Optional[str] = None,
    ) -> tuple[str, Dict[str, Any]]:
        import base64
        used_model = model_name or "local-model"
        if used_model.startswith("lmstudio:"):
            used_model = used_model[9:].strip()
        elif used_model.startswith("local:"):
            used_model = used_model[6:].strip()
        logger.info("LMStudioProvider: Calling LM Studio model %s", used_model)


        # Extract base64 image frames if multimodal payload is supplied
        images_b64: List[str] = []
        if isinstance(contents_payload, list):
            for part in contents_payload:
                if hasattr(part, "inline_data") and hasattr(part.inline_data, "data"):
                    b = part.inline_data.data
                    if isinstance(b, bytes):
                        images_b64.append(base64.b64encode(b).decode("utf-8"))
                elif isinstance(part, bytes):
                    images_b64.append(base64.b64encode(part).decode("utf-8"))

        t0 = time.monotonic()
        data = await asyncio.to_thread(self._sync_generate, used_model, prompt, images_b64 or None)
        elapsed_ms = max(1, int((time.monotonic() - t0) * 1000))

        choices = data.get("choices", [])
        if not choices or not isinstance(choices, list):
            raise ClippyMeError(f"LM Studio returned empty or invalid choices for model {used_model}")

        message = choices[0].get("message", {})
        raw_response = message.get("content", "")
        if not raw_response or not str(raw_response).strip():
            raise ClippyMeError(f"LM Studio returned empty response for model {used_model}")

        raw_response_text = str(raw_response)
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens") or max(1, len(prompt) // 4)
        candidate_tokens = usage.get("completion_tokens") or max(1, len(raw_response_text) // 4)
        total_tokens = usage.get("total_tokens") or (prompt_tokens + candidate_tokens)

        telemetry_data = {
            "provider": "lm_studio",
            "model": f"lmstudio:{used_model}",
            "model_used": f"lmstudio:{used_model}",
            "prompt_tokens": prompt_tokens,
            "candidate_tokens": candidate_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": 0.0,
            "cost_usd": 0.0,
            "latency_ms": elapsed_ms,
            "prompt": prompt,
            "raw_response": raw_response_text,
        }
        return raw_response_text, telemetry_data


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
    video_context: Optional[Union[Any, Dict[str, Any]]] = None,
) -> str:
    """Build the prompt for Gemini affiliate copy generation. Pure function.

    Generates instructions in Brazilian Portuguese (PT-BR) tailored for
    high-converting affiliate videos (Instagram Reels / TikTok / YouTube Shorts).
    """
    brand_name = _extract_field(brand, "name", "Achadinhos")
    brand_handle = _extract_field(brand, "handle", "@achadinhos")
    default_cta = _extract_field(brand, "default_cta", "Confira os achadinhos no link da bio!")
    brand_tone = (
        _extract_field(brand, "tone")
        or _extract_field(brand, "tone_of_voice")
        or _extract_field(_extract_field(brand, "publishing_profiles", {}), "tone")
        or "Entusiasmado, curioso e direto (estilo Achadinhos viral)"
    )

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

    context_lines = []
    if video_context is not None:
        vc_original_caption = _extract_field(video_context, "original_caption", "")
        vc_transcript = _extract_field(video_context, "transcript", "")
        vc_title = _extract_field(video_context, "title", "")
        vc_tags = _extract_field(video_context, "tags", [])
        vc_keyframes = _extract_field(video_context, "keyframes", [])
        vc_scenes = _extract_field(video_context, "scenes_count", 0)

        if vc_original_caption and str(vc_original_caption).strip():
            context_lines.append(f"- Legenda / descrição original do post: \"{str(vc_original_caption).strip()}\"")
        if vc_transcript and str(vc_transcript).strip():
            context_lines.append(f"- Transcrição do áudio falado no vídeo: \"{str(vc_transcript).strip()}\"")
        if vc_title and str(vc_title).strip():
            context_lines.append(f"- Título do post original: \"{str(vc_title).strip()}\"")
        if vc_tags and isinstance(vc_tags, list) and len(vc_tags) > 0:
            clean_tags = [str(t) for t in vc_tags if str(t).strip()]
            if clean_tags:
                context_lines.append(f"- Tags / tópicos originais: {', '.join(clean_tags)}")
        if vc_keyframes and isinstance(vc_keyframes, list) and len(vc_keyframes) > 0:
            context_lines.append(
                f"- Foram fornecidos {len(vc_keyframes)} frames visuais capturados das cenas do vídeo para análise visual direta do produto."
            )
        elif vc_scenes and vc_scenes > 0:
            context_lines.append(f"- O vídeo possui {vc_scenes} cena(s) identificadas.")

    context_section = ""
    if context_lines:
        context_section = "--- CONTEXTO EXTRAÍDO DO VÍDEO ---\n" + "\n".join(context_lines) + "\n\n"

    prompt = (
        "Você é um especialista em marketing de afiliados brasileiro e copywriter de vídeos virais "
        "para Instagram Reels, TikTok e YouTube Shorts (formato 'Achadinhos').\n"
        "Sua missão é analisar o produto demonstrado e produzir textos comerciais de alta conversão "
        "em Português Brasileiro (PT-BR).\n\n"
        "--- CONTEXTO DA MARCA ---\n"
        f"- Nome da marca: {brand_name}\n"
        f"- Perfil / Handle: {brand_handle}\n"
        f"- Tom de voz da marca: {brand_tone}\n"
        f"- CTA padrão da marca: {default_cta}\n"
        f"{code_instruction}"
        f"{url_instruction}"
        f"{user_instructions}\n"
        f"{context_section}"
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
        "   - NUNCA use chamadas como 'Comente QUERO que eu envio no direct' nem promessas de automação por direct/DM.\n"
        "   - NUNCA use promessas enganosas, links falsos ou comissões fictícias.\n\n"
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

    # Level 1: Standard JSON parse (strict=False permits literal newlines/tabs inside strings)
    try:
        data = json.loads(json_candidate, strict=False)
        if isinstance(data, dict):
            parsed_obj = data
    except (json.JSONDecodeError, ValueError):
        pass

    # Level 2: Deterministic clean + strict=False
    if parsed_obj is None:
        try:
            cleaned = _clean_json_str(json_candidate)
            data = json.loads(cleaned, strict=False)
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
    if isinstance(raw_headlines, str):
        raw_headlines = [
            re.sub(r"^(?:[-*•–—]|\d+[\.\-\)])\s*", "", line.strip())
            for line in raw_headlines.splitlines()
            if line.strip()
        ]
    if isinstance(raw_headlines, list):
        for h in raw_headlines:
            if isinstance(h, str) and h.strip():
                clean_h = h.strip()
                clean_h = re.sub(r"^(?:[-*•–—]|\d+[\.\-\)])\s*", "", clean_h)
                if clean_h and clean_h[:300] not in headlines:
                    headlines.append(clean_h[:300])

    if not headlines:
        headlines = list(DEFAULT_FALLBACK_HEADLINES)
    elif len(headlines) < 5:
        # Pad up to 5 with diverse fallback headlines
        for fallback_h in DEFAULT_FALLBACK_HEADLINES:
            if fallback_h not in headlines:
                headlines.append(fallback_h)
            if len(headlines) >= 5:
                break

    # Selected headline resolution
    raw_selected = str(data.get("selected_headline") or "").strip()
    selected_headline = re.sub(r"^(?:[-*•–—]|\d+[\.\-\)])\s*", "", raw_selected).strip()

    # Handle option index references: "Opção 2", "Opcao 3", "Option 4", "2", "Opção 3: Texto"
    option_m = re.match(
        r"^(?:op[çc][ãa]o|option)?\s*([1-9]|10)\b(?:\s*[:\-\.]\s*(.*))?$",
        raw_selected,
        re.IGNORECASE,
    )
    if option_m:
        opt_idx = int(option_m.group(1)) - 1
        tail = (option_m.group(2) or "").strip()
        if tail:
            selected_headline = tail
        elif 0 <= opt_idx < len(headlines):
            selected_headline = headlines[opt_idx]
        else:
            selected_headline = headlines[0]

    if not selected_headline:
        selected_headline = headlines[0]
    elif selected_headline not in headlines:
        headlines.insert(0, selected_headline)

    # Strictly clamp to 10 headlines AFTER any insertions
    headlines = headlines[:10]
    selected_headline = selected_headline[:300]

    # Hashtags
    raw_hashtags = data.get("hashtags")
    hashtags: List[str] = []
    if isinstance(raw_hashtags, str):
        # Support string format: "#achadinhos #cozinha #dicas" or comma separated
        raw_hashtags = re.findall(r"#?[\w-]+", raw_hashtags)
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
    raw_caption = data.get("caption")
    if isinstance(raw_caption, list):
        caption = "\n\n".join(str(p).strip() for p in raw_caption if str(p).strip())
    else:
        caption = str(raw_caption or "").strip()

    clean_code = str(product_code).strip() if (product_code is not None and str(product_code).strip()) else ""
    if not caption:
        # Assemble structured caption
        parts = [selected_headline]
        if product_desc:
            parts.append(product_desc)
        if clean_code:
            parts.append(f"📌 Produto {clean_code}")
        parts.append(default_cta)
        parts.append(" ".join(hashtags))
        caption = "\n\n".join(parts)
    else:
        # Guarantee product code is in caption if provided
        if clean_code:
            has_code = bool(
                re.search(
                    rf"(?:produto|código|codigo|cod\.?|ref\.?)\s*:?\s*#?{re.escape(clean_code)}\b",
                    caption,
                    re.IGNORECASE,
                )
                or f"📌 Produto {clean_code}" in caption
                or f"Código: {clean_code}" in caption
            )
            if not has_code:
                extra = f"📌 Produto {clean_code}"
                # If caption ends with hashtags block, insert code before hashtags
                tag_tail_m = re.search(r"(\n+(?:#[\w-]+\s*)+)$", caption)
                if tag_tail_m:
                    head = caption[: tag_tail_m.start()].rstrip()
                    tail = tag_tail_m.group(1).lstrip()
                    cand = f"{head}\n\n{extra}\n\n{tail}"
                else:
                    cand = f"{caption}\n\n{extra}"

                if len(cand) <= 2200:
                    caption = cand
                else:
                    caption = f"{cand[:2200 - len(extra) - 2]}\n\n{extra}"

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
    clean_code = str(product_code).strip() if (product_code is not None and str(product_code).strip()) else ""
    if clean_code:
        parts.append(f"📌 Produto {clean_code}")
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
    video_context: Optional[Union[Any, Dict[str, Any]]] = None,
) -> AICopyData:
    """Generate affiliate copy for a viral item with caching and model fallback.

    - Checks item-level cache first: returns cached copy immediately if present.
    - Resolves Gemini API key and fallback model ladder.
    - Extracts multi-signal video context & keyframes if video is provided.
    - Executes async content generation (multimodal with frame image parts).
    - Parses and validates response with multi-level repair.
    - Caches copy and ai_context_summary on item and persists to viral_studio_store.
    """
    # 1. Caching check: bypass Gemini if item already has ai_copy
    existing_copy = _extract_field(item, "ai_copy")
    if existing_copy is not None:
        copy_obj: Optional[AICopyData] = None
        if isinstance(existing_copy, AICopyData):
            copy_obj = existing_copy.model_copy()
        elif isinstance(existing_copy, dict):
            try:
                copy_obj = AICopyData.model_validate(existing_copy)
            except Exception:
                pass
        if copy_obj is not None:
            # Reconcile manual headline override and custom caption on item
            effective_selected_headline = (
                _extract_field(item, "manual_headline")
                or _extract_field(item, "selected_headline")
                or copy_obj.selected_headline
            )
            clean_headline = str(effective_selected_headline or "").strip()
            if not clean_headline:
                clean_headline = copy_obj.headlines[0] if copy_obj.headlines else DEFAULT_FALLBACK_HEADLINES[0]
            copy_obj.selected_headline = clean_headline[:300]
            if clean_headline not in copy_obj.headlines:
                copy_obj.headlines.insert(0, clean_headline[:300])
            copy_obj.headlines = copy_obj.headlines[:10]

            effective_caption = _extract_field(item, "caption") or copy_obj.caption
            copy_obj.caption = effective_caption

            # Update in-memory item
            if isinstance(item, dict):
                item["ai_copy"] = copy_obj.model_dump()
                item["selected_headline"] = clean_headline
                item["caption"] = effective_caption
                if video_path and not item.get("source_path"):
                    item["source_path"] = video_path
            else:
                try:
                    item.ai_copy = copy_obj
                    item.selected_headline = clean_headline
                    item.caption = effective_caption
                    if video_path and not getattr(item, "source_path", None):
                        item.source_path = video_path
                except Exception as e:
                    logger.debug("Could not assign fields directly to item object: %s", e)

            # Persist update to store if item has an ID
            item_id = _extract_field(item, "id") or _extract_field(item, "item_id")
            if item_id:
                try:
                    from clippyme.domain import viral_studio_store

                    viral_studio_store.update_item(
                        item_id,
                        {
                            "ai_copy": copy_obj.model_dump(),
                            "selected_headline": clean_headline,
                            "caption": effective_caption,
                        },
                    )
                except Exception as exc:
                    logger.debug("Could not persist cached copy update to store: %s", exc)

            logger.info("generate_affiliate_copy: Returning cached AICopyData for item")
            return copy_obj

    # 2. Resolve model and provider
    configured_model = (
        model
        or _extract_field(item, "model")
        or load_persistent_config().get("DEFAULT_AI_MODEL")
        or load_persistent_config().get("GEMINI_MODEL")
        or "gemini-3.5-flash"
    )
    provider_name, model_subname = parse_model_identifier(configured_model)

    # 3. Multi-Signal Video Context extraction (if video file is available and context not supplied)
    resolved_context = video_context
    target_video_file = video_path or _extract_field(item, "source_path")
    if resolved_context is None and target_video_file and os.path.isfile(target_video_file):
        try:
            from clippyme.domain.viral_studio_context import extract_viral_context

            resolved_context = extract_viral_context(
                video_path=target_video_file,
                source_metadata=_extract_field(item, "source_metadata"),
                batch_id=_extract_field(item, "batch_id"),
                item_id=_extract_field(item, "id") or _extract_field(item, "item_id"),
            )
        except Exception as exc:
            logger.debug("Automatic video context extraction skipped: %s", exc)

    context_summary = None
    if resolved_context is not None:
        if hasattr(resolved_context, "to_summary_dict"):
            context_summary = resolved_context.to_summary_dict()
        elif isinstance(resolved_context, dict):
            context_summary = resolved_context

    # 4. Build prompt with context
    product_code = _extract_field(item, "product_code")
    product_url = _extract_field(item, "product_url")
    instructions = (
        _extract_field(item, "additional_instructions")
        or _extract_field(item, "manual_instructions")
    )
    default_cta = _extract_field(brand, "default_cta") or "Confira os achadinhos no link da bio!"

    prompt = build_affiliate_copy_prompt(
        brand=brand,
        product_code=product_code,
        product_url=product_url,
        manual_instructions=instructions,
        video_context=resolved_context,
    )

    # 5. Prepare multimodal payload with frame images if available
    contents_payload: Any = prompt
    keyframes = _extract_field(resolved_context, "keyframes", [])
    if keyframes and isinstance(keyframes, list):
        try:
            from google.genai import types

            image_parts = []
            for kf in keyframes:
                if isinstance(kf, bytes) and len(kf) > 0:
                    image_parts.append(types.Part.from_bytes(data=kf, mime_type="image/jpeg"))
            if image_parts:
                contents_payload = [*image_parts, prompt]
        except Exception as exc:
            logger.debug("Could not attach visual frame parts: %s", exc)

    # 6. Execute generation via resolved provider
    if provider_name in ("lmstudio", "local", "lm_studio"):
        lm_prov = LMStudioProvider()
        raw_response_text, telemetry_data = await lm_prov.generate_copy(
            prompt=prompt,
            model_name=model_subname,
            contents_payload=contents_payload,
            api_key=api_key,
        )
    elif provider_name == "ollama":
        ollama_prov = OllamaProvider()
        raw_response_text, telemetry_data = await ollama_prov.generate_copy(
            prompt=prompt,
            model_name=model_subname,
            contents_payload=contents_payload,
            api_key=api_key,
        )
    else:
        gemini_prov = GeminiProvider()
        raw_response_text, telemetry_data = await gemini_prov.generate_copy(
            prompt=prompt,
            model_name=model_subname,
            contents_payload=contents_payload,
            api_key=api_key,
        )

    # 7. Parse and validate response
    copy_data = parse_affiliate_copy_response(
        raw_text=raw_response_text,
        default_cta=default_cta,
        product_code=product_code,
    )

    # 9. Reconcile with existing user edits (preserving custom captions/headlines)
    effective_selected_headline = (
        _extract_field(item, "manual_headline")
        or _extract_field(item, "selected_headline")
        or copy_data.selected_headline
    )
    clean_effective_headline = str(effective_selected_headline or "").strip()
    if not clean_effective_headline:
        clean_effective_headline = copy_data.selected_headline or (
            copy_data.headlines[0] if copy_data.headlines else DEFAULT_FALLBACK_HEADLINES[0]
        )
    copy_data.selected_headline = clean_effective_headline[:300]
    effective_caption = _extract_field(item, "caption") or copy_data.caption
    copy_data.caption = effective_caption
    if clean_effective_headline not in copy_data.headlines:
        copy_data.headlines.insert(0, clean_effective_headline[:300])
    copy_data.headlines = copy_data.headlines[:10]

    keyframe_urls = getattr(resolved_context, "keyframe_urls", []) if resolved_context else []

    if isinstance(item, dict):
        item["ai_copy"] = copy_data.model_dump()
        item["selected_headline"] = clean_effective_headline
        item["caption"] = effective_caption
        item["ai_telemetry"] = telemetry_data
        if keyframe_urls:
            item["keyframe_urls"] = keyframe_urls
        if context_summary:
            item["ai_context_summary"] = context_summary
        if video_path and not item.get("source_path"):
            item["source_path"] = video_path
    else:
        try:
            item.ai_copy = copy_data
            item.selected_headline = clean_effective_headline
            item.caption = effective_caption
            item.ai_telemetry = telemetry_data
            if keyframe_urls:
                item.keyframe_urls = keyframe_urls
            if context_summary:
                item.ai_context_summary = context_summary
            if video_path and not getattr(item, "source_path", None):
                item.source_path = video_path
        except Exception as e:
            logger.debug("Could not assign ai_copy directly to item object: %s", e)

    # 10. Persist to store if item has an ID
    item_id = _extract_field(item, "id") or _extract_field(item, "item_id")
    if item_id:
        try:
            from clippyme.domain import viral_studio_store
            update_dict: Dict[str, Any] = {
                "ai_copy": copy_data.model_dump(),
                "selected_headline": clean_effective_headline,
                "caption": effective_caption,
                "ai_telemetry": telemetry_data,
            }
            if context_summary:
                update_dict["ai_context_summary"] = context_summary
            if keyframe_urls:
                update_dict["keyframe_urls"] = keyframe_urls
            viral_studio_store.update_item(item_id, update_dict)
        except Exception as exc:
            logger.debug("Could not persist ai_copy to viral_studio_store: %s", exc)

    return copy_data


__all__ = [
    "build_affiliate_copy_prompt",
    "parse_affiliate_copy_response",
    "generate_affiliate_copy",
    "parse_model_identifier",
    "BaseAIProvider",
    "GeminiProvider",
    "OllamaProvider",
    "LMStudioProvider",
]
