"""Pure chunk extraction agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
import structlog

from backend.config import settings
from backend.intelligence.models import ChunkInsights

logger = structlog.get_logger(__name__)

load_dotenv()

INSTRUCTIONS = """
You are extracting comprehensive insights from a meeting transcript segment.

STRICT RULES:
1. ONLY extract what is EXPLICITLY stated - no inference or elaboration
2. SKIP trivial content (greetings, "OK", "Yeah", meeting logistics)
3. NEVER add information not in the transcript
4. If unsure, leave it out

EXTRACT:
- Technical explanations as stated (no adding details)
- Decisions with the reasoning given
- Important Q&A exchanges
- Action items with owners if named
- Key discussion points and context

Quality check each insight:
- Is this exactly what was said?
- Does it add value to understanding?
- Am I adding any information not stated?

Target: 10-20 meaningful insights per chunk
"""

chunk_extraction_agent = Agent(
    OpenAIResponsesModel(settings.insights_model),
    output_type=ChunkInsights,
    instructions=INSTRUCTIONS,
    retries=2,
)
