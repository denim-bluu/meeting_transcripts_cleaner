"""Pure transcript review agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
import structlog

from backend.config import settings
from backend.transcript.models import ReviewResult
from backend.utils.model_settings import build_openai_model_settings

logger = structlog.get_logger(__name__)

# Ensure environment is loaded for API key
load_dotenv()

# Agent configuration as module constants
REVIEWER_SYSTEM_PROMPT = """You are an expert transcript quality reviewer with deep expertise in meeting transcription standards.

Your task: Evaluate the quality of transcript cleaning with rigorous standards.

Evaluation Criteria:
1. Speaker Attribution (25%): Names preserved exactly, no confusion
2. Meaning Preservation (30%): Original intent and content maintained
3. Grammar & Clarity (25%): Proper grammar, clear sentence structure
4. Flow & Naturalness (20%): Conversational tone, natural transitions

Quality Scoring:
- 0.9-1.0: Excellent - Ready for publication
- 0.8-0.89: Good - Minor issues, acceptable
- 0.7-0.79: Fair - Some issues, needs review
- 0.6-0.69: Poor - Significant problems
- Below 0.6: Unacceptable - Major errors

Output format: JSON with exactly these fields:
- "quality_score": Float 0.0-1.0 overall quality assessment
- "issues": Array of specific problems found (empty if none)
- "accept": Boolean whether cleaning meets quality standards (score >= 0.7)"""

REVIEWER_USER_PROMPT = """Original transcript:
{original_text}

Cleaned version:
{cleaned_text}

Evaluate the cleaning quality and return JSON with quality_score, issues, and accept."""

# Pure agent definition - stateless and global
review_agent = Agent(
    OpenAIResponsesModel(settings.review_model),
    output_type=ReviewResult,
    system_prompt=REVIEWER_SYSTEM_PROMPT,
    retries=3,  # Built-in retry on validation failure
    model_settings=build_openai_model_settings(
        settings.review_model,
        reasoning_effort="medium",
    ),
)
logger.info("Review agent configured", review_model=settings.review_model)
