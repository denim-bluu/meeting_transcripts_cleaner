"""Pure transcript cleaning agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModel
import structlog

from backend.config import settings
from backend.transcript.models import CleaningResult
from backend.utils.model_settings import build_openai_model_settings

logger = structlog.get_logger(__name__)

# Ensure environment is loaded for API key
load_dotenv()

# Agent configuration as module constants
CLEANER_SYSTEM_PROMPT = """You are an expert transcript editor specializing in meeting transcripts.

Your task: Clean speech-to-text errors while preserving speaker attribution and conversational flow.

Rules:
1. NEVER change speaker names or labels
2. Fix grammar, spelling, and punctuation
3. Remove filler words (um, uh, like, you know)
4. Maintain conversational tone and meaning
5. Preserve technical terms and proper nouns
6. Keep the same general length and structure

Output format: JSON with exactly these fields:
- "cleaned_text": The improved transcript text
- "confidence": Float 0.0-1.0 indicating your confidence in the improvements
- "changes_made": Array of strings describing what was changed"""

# Pure agent definition - stateless and global
cleaning_agent = Agent(
    OpenAIResponsesModel(settings.cleaning_model),
    output_type=CleaningResult,
    system_prompt=CLEANER_SYSTEM_PROMPT,
    deps_type=dict,  # Accept context dictionary for tools
    retries=3,  # Built-in retry on validation failure
    model_settings=build_openai_model_settings(
        settings.cleaning_model,
        reasoning_effort="medium",
    ),
)
logger.info("Cleaning agent configured", cleaning_model=settings.cleaning_model)


# Add tools for dynamic context (following Pydantic AI patterns)
@cleaning_agent.tool
def provide_context_window(ctx: RunContext[dict], prev_text: str) -> str:
    """Provide context from previous chunk for better flow preservation."""
    return prev_text[-200:] if prev_text else ""
