"""Agent configuration for semantic aggregation of meeting summaries."""

from __future__ import annotations

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import (
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
import structlog

from backend.config import settings
from backend.intelligence.models import AggregationAgentPayload

load_dotenv()
logger = structlog.get_logger(__name__)

AGGREGATION_MODEL_NAME = getattr(settings, "aggregation_model", None) or settings.synthesis_model

AGGREGATION_INSTRUCTIONS = """
You synthesize meeting intelligence from structured chunk summaries.

Input: JSON array of IntermediateSummary objects along with conversation state and guidance.
Goals:
- Merge related concepts into meeting-specific key areas.
- Preserve temporal order and note decision cascades.
- Ensure each decision retains rationale and ownership (who confirmed it).
- Consolidate action items, merging duplicates while preserving owners.
- Flag contradictions or unresolved items in validation_notes.

Output must conform to AggregationAgentPayload.
- summary_markdown: multi-section markdown telling the meeting story in order.
- key_areas: 3-6 clusters, each with summary, bullet_points, decisions, action_items, supporting_chunks, temporal_span, confidence.
- consolidated_action_items: deduplicated list across the meeting.
- timeline_events: short bullet timeline with timestamps or chunk ids.
- unresolved_topics: questions or issues still open at end of meeting.
- validation_notes: any concerns about missing context or ambiguity.
- confidence: overall confidence (0-1).
"""


aggregation_agent = Agent(
    OpenAIResponsesModel(AGGREGATION_MODEL_NAME),
    output_type=AggregationAgentPayload,
    instructions=AGGREGATION_INSTRUCTIONS,
    retries=2,
    model_settings=OpenAIResponsesModelSettings(
        openai_reasoning_effort="high",
        openai_reasoning_summary="detailed",
    ),
)

logger.info(
    "Aggregation agent configured",
    aggregation_model=AGGREGATION_MODEL_NAME,
)
