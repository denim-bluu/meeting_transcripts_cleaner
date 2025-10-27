"""Agent configuration for semantic aggregation of meeting summaries."""

from __future__ import annotations

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
import structlog

from backend.config import settings
from backend.intelligence.models import AggregationAgentPayload
from backend.utils.model_settings import build_openai_model_settings

load_dotenv()
logger = structlog.get_logger(__name__)

AGGREGATION_MODEL_NAME = settings.aggregation_model

AGGREGATION_INSTRUCTIONS = """
You synthesize meeting intelligence from structured chunk summaries.

Input: JSON array of IntermediateSummary objects along with conversation state and guidance.
Goals:
- Create 3-5 narrative sections that walk through the meeting chronologically.
- Merge related concepts into meeting-specific key areas with decision cascades and action ownership.
- Consolidate action items, merging duplicates while preserving owners and due dates.
- Flag contradictions or unresolved items in validation_notes so downstream validation can act.
- Skip standalone sections that only cover greetings, pleasantries, or scheduling notes unless they directly influence later decisions.

Output must conform to AggregationAgentPayload with these expectations:
- sections: ordered list of narrative blocks. Required titles (case-insensitive): "Key Decisions & Outcomes", "Priorities & Projects", and "Action Items & Ownership". Each block needs a title, 2-4 bullet_points, and an overview paragraph.
- For every section and bullet, populate related_chunks with the chunk ids (or ids of the speakers' turns) that back the statement.
- key_areas: 3-6 clusters, each with summary, bullet_points, decisions, action_items, supporting_chunks, temporal_span, confidence.
- consolidated_action_items: deduplicated list across the meeting with owners and due dates when present.
- timeline_events: short bullet timeline anchored by timestamps or chunk ids.
- unresolved_topics: explicit questions or TODOs that remained open.
- validation_notes: concerns about missing context, contradictions, or weak evidence.
- confidence: overall confidence (0-1) in the aggregated interpretation.
"""


aggregation_agent = Agent(
    OpenAIResponsesModel(AGGREGATION_MODEL_NAME),
    output_type=AggregationAgentPayload,
    instructions=AGGREGATION_INSTRUCTIONS,
    retries=2,
    model_settings=build_openai_model_settings(
        AGGREGATION_MODEL_NAME,
        reasoning_effort="high",
        reasoning_summary="detailed",
    ),
)

logger.info(
    "Aggregation agent configured",
    aggregation_model=AGGREGATION_MODEL_NAME,
)
