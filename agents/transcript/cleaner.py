"""Pure transcript cleaning agent - stateless and global following Pydantic AI best practices."""

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from models.agents import CleaningResult

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
    "openai:o3-mini",
    output_type=CleaningResult,
    system_prompt=CLEANER_SYSTEM_PROMPT,
    deps_type=dict,  # Accept context dictionary for tools
    retries=3,  # Built-in retry on validation failure
)


# Add tools for dynamic context (following Pydantic AI patterns)
@cleaning_agent.tool
def provide_context_window(ctx: RunContext[dict], prev_text: str) -> str:
    """Provide context from previous chunk for better flow preservation."""
    return prev_text[-200:] if prev_text else ""


# Model settings function for runtime configuration
def get_model_settings(model: str) -> ModelSettings | None:
    """Get appropriate model settings based on model type."""
    if model.startswith("o3"):
        return None  # o3 models don't support temperature/max_tokens
    else:
        return ModelSettings(temperature=0.3, max_tokens=1000)
