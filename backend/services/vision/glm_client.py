"""Vision-API client for any OpenAI-compatible chat endpoint.

Production default: the Google Gemini OpenAI-compatible layer
(https://generativelanguage.googleapis.com/v1beta/openai). Sends the palm
photo as a base64 data URL together with a prompt that forces a strict
JSON verdict, parses the response into a `DiagnosisResult`, and retries
transient failures (429/5xx with Retry-After, timeouts) with backoff.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from backend.core.config import Settings, get_settings
from backend.core.logging import get_logger
from backend.models import Severity
from backend.services.vision import knowledge_base as kb
from backend.services.vision.preprocessing import to_data_url
from backend.services.vision.results import (
    DiagnosisResult,
    ImageQuality,
    InferenceError,
    ProviderAuthError,
)

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are an expert agronomist specialising in date palm "
    "(Phoenix dactylifera) health. You diagnose pests, diseases and "
    "nutrient disorders from photos of trunks, crowns, fronds and fruit. "
    "You answer ONLY with a single JSON object — no markdown fences, no "
    "commentary."
)

USER_PROMPT = """Analyse this date palm image for pests, diseases and \
nutrient disorders.

Consider in particular: Red Palm Weevil (Rhynchophorus ferrugineus) \
damage, Graphiola leaf spot, Diplodia bud/frond rot, Pestalotiopsis \
leaf spot, Fusarium wilt (Bayoud), leaf rust, fruit/bunch rots, and \
potassium, magnesium or nitrogen deficiencies.

Return exactly this JSON object:
{
  "is_healthy": <boolean>,
  "detected_disease": <string or null>,
  "severity": "low" | "medium" | "high" | null,
  "confidence": <number 0.0-1.0>,
  "symptoms": [<string>, ...],
  "treatment_steps": [<string>, ...],
  "assessment": <one-paragraph summary>
}

Rules:
- If the palm looks healthy: is_healthy=true, detected_disease=null, \
severity=null, symptoms may list minor observations.
- confidence reflects how clearly the visual evidence supports the \
verdict, 1.0 = certain.
- treatment_steps must be concrete, actionable field measures.
- Never invent symptoms that are not visible."""

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class TransientAPIError(InferenceError):
    """Retryable HTTP failure (429/5xx) raised to trigger tenacity."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        #: Seconds the provider asked us to wait (Retry-After header).
        self.retry_after = retry_after


def _wait_with_retry_after(retry_state) -> float:
    """Exponential jitter, raised to the provider's Retry-After when sent."""
    exponential = wait_exponential_jitter(initial=2.0, max=15.0)(retry_state)
    outcome = retry_state.outcome
    if outcome is not None and outcome.failed:
        exc = outcome.exception()
        retry_after = getattr(exc, "retry_after", None)
        if retry_after:
            return max(exponential, float(retry_after))
    return exponential


class GLMVisionClient:
    """Async client for the GLM-4V chat-completions endpoint."""

    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_attempts: int = 4,
        initial_retry_wait: float = 1.0,
    ) -> None:
        self._settings = settings or get_settings()
        self._transport = transport  # injected in tests via httpx.MockTransport
        self._max_attempts = max_attempts
        self._initial_retry_wait = initial_retry_wait

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def analyze(
        self,
        jpeg_bytes: bytes,
        quality: ImageQuality,
        filename: str = "image.jpg",
        context_note: str | None = None,
    ) -> DiagnosisResult:
        """Run the diagnosis request and return the structured result."""
        started = time.monotonic()
        content = await self._request_completion(jpeg_bytes, context_note)
        payload = self._extract_json(content)
        result = self._to_result(
            payload, quality, started, model=self._settings.GLM_VISION_MODEL
        )
        logger.info(
            "GLM diagnosis for %s: disease=%s severity=%s confidence=%.2f "
            "(%d ms)",
            filename,
            result.detected_disease,
            result.severity.value if result.severity else None,
            result.confidence,
            result.latency_ms,
        )
        return result

    # ------------------------------------------------------------------
    # HTTP layer
    # ------------------------------------------------------------------
    async def _request_completion(
        self, jpeg_bytes: bytes, context_note: str | None = None
    ) -> str:
        """POST the image to the API with retries; returns message content."""
        api_key = self._settings.GLM_API_KEY
        if api_key is None:
            raise InferenceError(
                "GLM_API_KEY is not configured — set it in .env to use the "
                "GLM vision provider."
            )

        prompt_text = USER_PROMPT
        if context_note:
            prompt_text += (
                f"\n\nRegistered tree context (trust but verify visually): "
                f"{context_note}"
            )

        request_body = {
            "model": self._settings.GLM_VISION_MODEL,
            "temperature": 0.1,
            # Explicit budget: thinking models (e.g. gemini-2.5-flash) spend
            # output tokens on internal reasoning — an unset/low cap truncates
            # the JSON verdict mid-object.
            "max_tokens": 3000,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": to_data_url(jpeg_bytes)},
                        },
                        {"type": "text", "text": prompt_text},
                    ],
                },
            ],
        }

        async with httpx.AsyncClient(
            base_url=self._settings.GLM_API_BASE.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            timeout=self._settings.INFERENCE_TIMEOUT_SECONDS,
            transport=self._transport,
        ) as client:
            try:
                strategy = AsyncRetrying(
                    retry=retry_if_exception_type(
                        (TransientAPIError, httpx.TimeoutException, httpx.TransportError)
                    ),
                    stop=stop_after_attempt(self._max_attempts),
                    wait=_wait_with_retry_after,
                    reraise=True,
                )
                response = await strategy.__call__(
                    self._post_once, client, request_body
                )
            except (TransientAPIError, httpx.TimeoutException, httpx.TransportError) as exc:
                raise InferenceError(
                    f"GLM API unreachable after {self._max_attempts} attempts: {exc}"
                ) from exc

        return self._message_content(response)

    async def _post_once(
        self, client: httpx.AsyncClient, request_body: dict[str, Any]
    ) -> httpx.Response:
        """Single POST attempt; raises TransientAPIError on 429/5xx."""
        response = await client.post("/chat/completions", json=request_body)
        if response.status_code in _RETRYABLE_STATUS:
            retry_after = None
            header = response.headers.get("Retry-After")
            if header:
                try:  # both seconds-form and HTTP-date form exist; use seconds
                    retry_after = min(float(header), 30.0)
                except ValueError:
                    retry_after = None
            raise TransientAPIError(
                f"GLM API transient failure: HTTP {response.status_code}",
                retry_after=retry_after,
            )
        if response.status_code in (401, 403) or (
            response.status_code == 400
            and "api key" in response.text.lower()
        ):
            # Credentials rejected — retrying cannot help; surface distinctly.
            # Gemini quirk: invalid keys arrive as 400 INVALID_ARGUMENT,
            # not 401.
            raise ProviderAuthError(
                f"Vision API key was rejected (HTTP {response.status_code}): "
                f"{response.text[:200]}"
            )
        if response.status_code >= 400:
            raise InferenceError(
                f"GLM API rejected the request: HTTP {response.status_code} — "
                f"{response.text[:300]}"
            )
        return response

    async def verify_connection(self) -> dict[str, Any]:
        """Cheap health probe of the provider for diagnostics.

        Sends a 1-token text ping: 401/403 proves a bad key, ANY other
        HTTP status proves authentication passed (even a 400 about the
        request shape means the key was accepted).
        """
        result: dict[str, Any] = {
            "provider": "glm",
            "model": self._settings.GLM_VISION_MODEL,
            "key_configured": False,
            "reachable": False,
            "authenticated": False,
            "detail": "",
        }
        api_key = self._settings.GLM_API_KEY
        if api_key is None:
            result["detail"] = (
                "GLM_API_KEY is not configured — set it in the environment "
                "and restart the service."
            )
            return result
        result["key_configured"] = True

        probe = {
            "model": self._settings.GLM_VISION_MODEL,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.GLM_API_BASE.rstrip("/"),
                headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
                timeout=15,
                transport=self._transport,
            ) as client:
                response = await client.post("/chat/completions", json=probe)
        except httpx.HTTPError as exc:
            result["detail"] = f"Cannot reach the GLM API: {exc}"
            return result

        result["reachable"] = True
        if response.status_code in (401, 403):
            result["detail"] = (
                f"API key rejected by the provider (HTTP {response.status_code}). "
                "Replace GLM_API_KEY with a valid key — retrying will not help."
            )
            return result
        result["authenticated"] = True
        result["detail"] = (
            "OK — provider reachable and key accepted."
            if response.status_code == 200
            else f"Key accepted (probe returned HTTP {response.status_code})."
        )
        return result

    @staticmethod
    def _message_content(response: httpx.Response) -> str:
        """Pull the assistant message text out of the API response."""
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise InferenceError(
                f"Unexpected GLM API response shape: {response.text[:300]}"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise InferenceError("GLM API returned an empty message.")
        return content

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        """Extract the JSON object from the model output, tolerating fences."""
        candidate: str | None = None

        fenced = _JSON_FENCE_RE.search(content)
        if fenced:
            candidate = fenced.group(1)
        else:
            start, end = content.find("{"), content.rfind("}")
            if start != -1 and end > start:
                candidate = content[start : end + 1]

        if candidate is None:
            raise InferenceError(
                f"No JSON object found in model output: {content[:200]!r}"
            )
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise InferenceError(
                f"Model output is not valid JSON: {candidate[:200]!r}"
            ) from exc
        if not isinstance(payload, dict):
            raise InferenceError("Model JSON is not an object.")
        return payload

    @staticmethod
    def _to_result(
        payload: dict[str, Any],
        quality: ImageQuality,
        started: float,
        model: str,
    ) -> DiagnosisResult:
        """Map the model JSON onto the validated DiagnosisResult contract."""
        raw_disease = payload.get("detected_disease")
        raw_disease = str(raw_disease).strip() if raw_disease else None
        catalog_entry = kb.lookup_disease(raw_disease)

        is_healthy = bool(payload.get("is_healthy", False)) or catalog_entry is None

        severity: Severity | None = None
        raw_severity = str(payload.get("severity") or "").strip().lower()
        if raw_severity in Severity._value2member_map_:
            severity = Severity(raw_severity)
        elif catalog_entry is not None and not is_healthy:
            severity = catalog_entry.default_severity

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = min(max(confidence, 0.0), 1.0)

        symptoms = [str(s) for s in payload.get("symptoms") or [] if str(s).strip()]
        raw_steps = payload.get("treatment_steps") or []
        treatment_steps = [str(s) for s in raw_steps if str(s).strip()]
        if not treatment_steps and catalog_entry is not None and not is_healthy:
            treatment_steps = list(catalog_entry.treatment_steps)

        display_name = (
            catalog_entry.display_name if catalog_entry else raw_disease
        )
        status = kb.derive_status(is_healthy, catalog_entry, severity)
        if is_healthy:
            display_name = None

        assessment = payload.get("assessment")
        assessment = str(assessment) if assessment else None

        # Knowledge-base grounding: cause + prevention come from the catalog
        # when the disease is known (the model may add detail via symptoms).
        cause = catalog_entry.cause if catalog_entry else None
        if catalog_entry:
            prevention = list(catalog_entry.prevention)
        elif not is_healthy:
            prevention = [
                ("Re-inspect the palm within 2 weeks and photograph any "
                "change."),
                "Consult a local agronomist for an on-site confirmation.",
            ]
        else:
            prevention = []

        return DiagnosisResult(
            detected_disease=display_name,
            severity=None if is_healthy else severity,
            confidence=confidence,
            status=status,
            symptoms=symptoms,
            treatment_steps=treatment_steps,
            cause=cause,
            prevention=prevention,
            assessment=assessment,
            provider="glm",
            model=model,
            latency_ms=int((time.monotonic() - started) * 1000),
            quality=quality,
        )
