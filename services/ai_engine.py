"""
AI engine: the single integration point for image analysis and
recommendations over farmer-logged Observations.

Design principles (mirrors pnl_engine.py / alert_engine.py):
  - The *interpretation* of a model's output into structured fields
    (category, confidence, recommendation) is a pure function, unit
    testable without any network access.
  - The actual provider call is isolated behind a small Protocol
    (AIProvider) so it's trivially mockable in tests and swappable if the
    underlying model/provider changes -- nothing outside this module needs
    to know which provider is in use.
  - Results are always advisory: this module never marks a ScheduleActivity
    complete, never auto-creates an Expense, and never overwrites a
    farmer's own note/image. It only ever populates the ai_* columns on an
    Observation (see repositories/observation_repo.save_ai_analysis), which
    a human can read, act on, or ignore.
  - A failed or unavailable provider call degrades to a clearly-labeled
    "analysis unavailable" result rather than raising -- a flaky AI
    integration should never break the core logging flow of just saving a
    photo and a note.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Protocol

ALLOWED_CATEGORIES = [
    "Pest",
    "Disease",
    "Nutrient Deficiency",
    "Water Stress",
    "Weed Pressure",
    "Healthy / No Issue",
    "Unclear",
]


@dataclass
class AIAnalysisResult:
    analysis: str
    category: str
    confidence: float  # 0.0 - 1.0
    recommendation: str
    raw_response: dict | None = None
    succeeded: bool = True


def _unavailable_result(reason: str) -> AIAnalysisResult:
    return AIAnalysisResult(
        analysis=f"Analysis unavailable: {reason}",
        category="Unclear",
        confidence=0.0,
        recommendation="Please try again later, or consult a local agronomist if the issue looks urgent.",
        raw_response=None,
        succeeded=False,
    )


class AIProvider(Protocol):
    """
    Minimal interface a vision-capable model provider must satisfy. Swap
    implementations (e.g. a different model, or a local/offline model for
    on-farm use with poor connectivity) without touching analyze_observation.
    """

    def analyze_image(self, image_bytes: bytes, media_type: str, prompt: str) -> dict:
        """Returns a parsed JSON-like dict matching the prompt's requested schema."""
        ...


class AnthropicVisionProvider:
    """
    Default AIProvider backed by the Anthropic Messages API. Lazily
    constructs its client so importing ai_engine never requires API
    credentials to be present (e.g. when only the pure parsing functions in
    this module are being unit tested).
    """

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        return self._client

    def analyze_image(self, image_bytes: bytes, media_type: str, prompt: str) -> dict:
        client = self._get_client()
        encoded = base64.standard_b64encode(image_bytes).decode("utf-8")

        response = client.messages.create(
            model=self.model,
            max_tokens=600,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": encoded},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        raw_text = "\n".join(text_blocks).strip()
        # Strip markdown code fences if the model wrapped its JSON in them.
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:].strip()
        return json.loads(raw_text)


def _build_prompt(crop_name: str, stage_name: str | None, farmer_note: str | None) -> str:
    context_lines = [f"Crop: {crop_name}"]
    if stage_name:
        context_lines.append(f"Current growth stage: {stage_name}")
    if farmer_note:
        context_lines.append(f"Farmer's note: {farmer_note}")
    context = "\n".join(context_lines)

    categories = ", ".join(ALLOWED_CATEGORIES)
    return (
        "You are an agronomy assistant helping a smallholder farmer interpret a field photo.\n"
        f"{context}\n\n"
        "Look at the attached photo and respond with ONLY a JSON object (no markdown, no preamble) "
        "with exactly these keys:\n"
        f'  "category": one of [{categories}]\n'
        '  "analysis": one or two plain sentences describing what you observe\n'
        '  "confidence": a number from 0.0 to 1.0 reflecting how confident you are\n'
        '  "recommendation": one practical, actionable next step for the farmer\n\n'
        "If the photo is unclear, blurry, or doesn't show enough of the plant to assess, "
        'use category "Unclear" and say so plainly rather than guessing.'
    )


def _parse_provider_response(raw: dict) -> AIAnalysisResult:
    """
    Pure function: turn whatever JSON-shaped dict a provider returned into a
    validated AIAnalysisResult, defensively handling missing/malformed
    fields so a slightly-off model response degrades gracefully instead of
    raising. Fully unit-testable with hand-built dicts, no network needed.
    """
    category = raw.get("category", "Unclear")
    if category not in ALLOWED_CATEGORIES:
        category = "Unclear"

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    analysis = str(raw.get("analysis") or "No analysis text returned.")
    recommendation = str(raw.get("recommendation") or "No specific recommendation available.")

    return AIAnalysisResult(
        analysis=analysis,
        category=category,
        confidence=confidence,
        recommendation=recommendation,
        raw_response=raw,
        succeeded=True,
    )


def analyze_observation(
    image_bytes: bytes,
    media_type: str,
    crop_name: str,
    stage_name: str | None = None,
    farmer_note: str | None = None,
    provider: AIProvider | None = None,
) -> AIAnalysisResult:
    """
    The single entry point the rest of the app should call to analyze an
    observation photo. Builds the prompt, calls the provider, parses the
    result -- and on ANY provider failure (network error, malformed JSON,
    missing credentials), returns a clearly-labeled unavailable result
    instead of raising, so a flaky AI call never breaks the page that's
    just trying to save a farmer's photo and note.
    """
    if provider is None:
        provider = AnthropicVisionProvider()

    prompt = _build_prompt(crop_name, stage_name, farmer_note)

    try:
        raw = provider.analyze_image(image_bytes, media_type, prompt)
    except Exception as exc:  # noqa: BLE001 - intentionally broad: any provider failure must degrade gracefully
        return _unavailable_result(str(exc))

    try:
        return _parse_provider_response(raw)
    except Exception as exc:  # noqa: BLE001
        return _unavailable_result(f"could not parse model response ({exc})")


def is_ai_configured() -> bool:
    """Whether the default provider has credentials available, for UI gating."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
