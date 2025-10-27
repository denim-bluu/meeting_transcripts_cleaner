"""Agent configuration for per-chunk meeting analysis."""

from __future__ import annotations

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
import structlog

from backend.config import settings
from backend.intelligence.models import ChunkAgentPayload
from backend.utils.model_settings import build_openai_model_settings

load_dotenv()
logger = structlog.get_logger(__name__)

CHUNK_PROCESSING_INSTRUCTIONS = """
You analyze exactly one speaker turn from a meeting and produce structured intelligence.

Non-negotiable rules:
- Cite only what appears in the transcript snippet or context JSON.
- Show how the speaker relates to prior discussion; set continuation_flag when the turn clearly continues an earlier idea.
- Treat decisions and action items with authority awareness; never invent an owner or commitment.
- Always capture concrete data (percentages, dollar amounts, metrics) and due dates verbatim when they are mentioned.
- When the speaker raises more than one idea, capture each as a separate concept bullet.
- If the turn is purely administrative (greetings, logistics), record it as a single low-importance concept and leave other collections empty.

Output must be valid JSON matching ChunkAgentPayload with these expectations:
- narrative_summary: 2-3 sentences summarising the turn and referencing earlier context where relevant.
- key_concepts: minimum of 2 entries unless the speaker covers only a single point; include title, detail, and importance (0-1).
- decisions: list confirmed or strongly implied decisions with rationale, authority, and numeric specifics where given.
- action_items: commitments with owner and explicit due date/timeline when stated; do not omit a due date if the transcript contains one.
- conversation_links: map explicit callbacks to prior chunks (choose link_type from follow_up, contrast, support, clarification, callback).
- insights: 1-2 headline/detail pairs to help reviewers scan the turn quickly.
- confidence: 0-1 float indicating certainty in the extracted data.
"""


CHUNK_MODEL_NAME = settings.chunk_model

chunk_processing_agent = Agent(
    OpenAIResponsesModel(CHUNK_MODEL_NAME),
    output_type=ChunkAgentPayload,
    instructions=CHUNK_PROCESSING_INSTRUCTIONS,
    retries=2,
    model_settings=build_openai_model_settings(
        CHUNK_MODEL_NAME,
        reasoning_effort="medium",
        reasoning_summary="detailed",
    ),
)

logger.info(
    "Chunk processing agent configured",
    chunk_model=CHUNK_MODEL_NAME,
)
