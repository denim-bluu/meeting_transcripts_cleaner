"""Pure Pydantic AI agent definitions following multi-agent best practices.

This module contains stateless, global agent definitions that can be imported
and used throughout the application. Agents are separated from business logic
and orchestration concerns.

Import patterns:
    # Import specific agents
    from agents.transcript import cleaning_agent, review_agent
    from agents.extraction import chunk_extraction_agent
    from agents.synthesis import direct_synthesis_agent

    # Import all agents (for convenience)
    from agents import *
"""

# Import all agents for convenient access
from backend.agents.extraction.insights import chunk_extraction_agent
from backend.agents.synthesis.direct import direct_synthesis_agent
from backend.agents.transcript.cleaner import cleaning_agent
from backend.agents.transcript.reviewer import review_agent

# Export all agents
__all__ = [
    "cleaning_agent",
    "review_agent",
    "chunk_extraction_agent",
    "direct_synthesis_agent",
]
