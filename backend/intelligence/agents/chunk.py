"""Agent configuration for per-chunk meeting analysis."""

from __future__ import annotations

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import (
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
import structlog

from backend.config import settings
from backend.intelligence.models import ChunkAgentPayload

load_dotenv()
logger = structlog.get_logger(__name__)

CHUNK_PROCESSING_INSTRUCTIONS = """
You analyze a single speaker's turn in a meeting transcript and extract structured intelligence.

Rules:
- Only use information from the provided transcript segment and context JSON.
- Respect temporal flow: note whether the speaker is continuing a prior idea.
- Capture decisions and action items with precise language; do not invent owners.
- Include continuation_flag = true when the statement appears incomplete or references pending details.

Output must be valid JSON conforming to ChunkAgentPayload. Field guidance:
- narrative_summary: 2-3 sentences describing this turn, referencing prior context if relevant.
- key_concepts: list of key ideas (title, detail, importance 0-1 if clear).
- decisions: only confirmed or strongly implied decisions with rationale.
- action_items: commitments with potential owners and due dates if mentioned.
- conversation_links: references to earlier discussion (link_type choose from follow_up, contrast, support, clarification, callback).
- insights: optional headline/detail pairs that will help humans trace the analysis.
- confidence: 0-1 float showing certainty of extracted data.
"""


CHUNK_MODEL_NAME = getattr(settings, "chunk_model", None) or settings.synthesis_model

chunk_processing_agent = Agent(
    OpenAIResponsesModel(CHUNK_MODEL_NAME),
    output_type=ChunkAgentPayload,
    instructions=CHUNK_PROCESSING_INSTRUCTIONS,
    retries=2,
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="medium",
        openai_reasoning_summary="detailed",
    ),
)

logger.info(
    "Chunk processing agent configured",
    chunk_model=CHUNK_MODEL_NAME,
)
