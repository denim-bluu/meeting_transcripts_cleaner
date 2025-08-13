"""AI agents for meeting intelligence extraction using Pydantic AI."""

import os
import time

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModelSettings
import structlog

from models.intelligence import ActionItem, ChunkSummary, IntelligenceResult

# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger(__name__)

# System prompts for intelligence extraction
SUMMARY_PROMPT = """You are an expert meeting analyst specializing in extracting key information from meeting segments.

Your task: Extract key information from this meeting segment.

Focus on:
- Main points discussed
- Decisions made
- Topics covered
- Speakers involved

Be concise and factual. Do not infer or add information not present in the text.

Return JSON with exactly these fields:
- "key_points": List of 1-5 main points (strings)
- "decisions": List of decisions made (can be empty)
- "topics": List of topics discussed (at least 1)
- "speakers": List of speakers in this segment (at least 1)
- "confidence": Float 0.0-1.0 indicating extraction quality"""

ACTION_PROMPT = """You are an expert meeting analyst specializing in identifying action items from meeting discussions.

Your task: Identify action items from this meeting segment.

Look for:
- Tasks assigned to specific people
- Commitments made by participants
- Follow-ups needed
- Deadlines mentioned
- Dependencies between tasks

Include owner if mentioned, deadline if specified.
Mark as critical if involves: budget, legal, strategic decisions, or high-impact business outcomes.

For each action item, return:
- "description": Clear description of the action (min 10 characters)
- "owner": Person responsible (if mentioned, otherwise null)
- "deadline": Due date (if mentioned, otherwise null)
- "dependencies": List of other tasks this depends on
- "source_chunks": List containing the current chunk ID
- "confidence": Float 0.0-1.0 indicating extraction confidence
- "is_critical": Boolean for critical business items
- "needs_review": Will be auto-calculated

Return a list of action items (can be empty if none found)."""

SYNTHESIS_PROMPT = """You are an expert meeting intelligence synthesizer specializing in creating comprehensive meeting summaries.

Your task: Synthesize all chunk-level extractions into cohesive meeting intelligence.

Process:
1. Deduplicate action items across chunks (merge similar items)
2. Merge related summaries coherently
3. Create executive summary (<500 characters)
4. Generate bullet points (3-10 key points)
5. Calculate overall confidence score
6. Maintain traceability to source chunks

Return JSON with exactly these fields:
- "executive_summary": Concise overview (<500 chars)
- "detailed_summary": Comprehensive summary (<2000 chars)
- "bullet_points": List of 3-10 key takeaways
- "action_items": Deduplicated list of action items
- "key_decisions": List of important decisions made
- "topics_discussed": List of main topics covered
- "confidence_score": Overall confidence (0.0-1.0)
- "processing_stats": Statistics about the processing"""


class SummaryExtractor:
    """
    Extracts summaries from individual chunks using Pydantic AI.

    Responsibilities:
    - Process enriched window (chunk + context)
    - Extract key points, decisions, topics
    - Calculate confidence based on extraction quality
    - Handle API failures gracefully

    Expected behavior:
    - Returns ChunkSummary with 1-5 key points
    - Uses GPT-4 with temperature=0.3 for consistency
    - Logs all extractions with timing metrics
    - Raises on API errors after 3 retries
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-4"):
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key

        self.model_name = model
        self.agent = Agent(
            f"openai:{model}",
            output_type=ChunkSummary,
            system_prompt=SUMMARY_PROMPT,
            retries=3,
        )

        logger.info(
            "SummaryExtractor initialized",
            model=model,
            supports_temperature=not model.startswith("o3"),
        )

    async def extract(self, window: dict) -> ChunkSummary:
        """
        Extract summary from context window.
        Input: {'chunk_id': int, 'full_context': str, 'speakers': List[str]}
        Output: ChunkSummary with extraction results
        """
        start_time = time.time()
        chunk_id = window["chunk_id"]
        full_context = window["full_context"]
        speakers = window["speakers"]

        logger.info(
            "Starting summary extraction",
            chunk_id=chunk_id,
            text_length=len(full_context),
            speakers=speakers,
            model=self.model_name,
        )

        user_prompt = f"""Analyze this meeting segment and extract key information:

Meeting segment:
{full_context}

Speakers in this segment: {', '.join(speakers)}

Extract the key points, decisions, topics, and calculate your confidence in the extraction."""

        try:
            # Use model settings for non-o3 models
            settings = (
                None
                if self.model_name.startswith("o3")
                else OpenAIModelSettings(temperature=0.3, max_tokens=800)
            )

            api_call_start = time.time()
            result = await self.agent.run(user_prompt, model_settings=settings)
            api_call_time = time.time() - api_call_start
            processing_time = time.time() - start_time

            logger.info(
                "Summary extraction completed",
                chunk_id=chunk_id,
                processing_time_ms=int(processing_time * 1000),
                api_call_time_ms=int(api_call_time * 1000),
                confidence=result.output.confidence,
                key_points_count=len(result.output.key_points),
                decisions_count=len(result.output.decisions),
                topics_count=len(result.output.topics),
                model=self.model_name,
            )

            return result.output

        except Exception as e:
            logger.error(
                "Summary extraction failed",
                chunk_id=chunk_id,
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
                model=self.model_name,
            )
            raise


class ActionItemExtractor:
    """
    Extracts action items from individual chunks using Pydantic AI.

    Responsibilities:
    - Identify tasks, assignments, commitments
    - Extract owner and deadline if present
    - Flag critical items (financial, legal, strategic)
    - Track confidence per item

    Expected behavior:
    - Returns List[ActionItem] (may be empty)
    - Detects implicit assignments ("someone should...")
    - Uses GPT-4 with temperature=0.2 for precision
    - Validates each item before returning
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-4"):
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key

        self.model_name = model
        self.agent = Agent(
            f"openai:{model}",
            output_type=list[ActionItem],
            system_prompt=ACTION_PROMPT,
            retries=3,
        )

        logger.info(
            "ActionItemExtractor initialized",
            model=model,
            supports_temperature=not model.startswith("o3"),
        )

    async def extract(self, window: dict) -> list[ActionItem]:
        """
        Extract action items from context window.
        Input: {'chunk_id': int, 'full_context': str}
        Output: List of ActionItems with source tracking
        """
        start_time = time.time()
        chunk_id = window["chunk_id"]
        full_context = window["full_context"]

        logger.info(
            "Starting action item extraction",
            chunk_id=chunk_id,
            text_length=len(full_context),
            model=self.model_name,
        )

        user_prompt = f"""Analyze this meeting segment and identify any action items:

Meeting segment:
{full_context}

Look for:
- Tasks assigned to people
- Commitments made
- Follow-up actions needed
- Deadlines mentioned
- Dependencies

For each action item found, set source_chunks to [{chunk_id}].
If no action items are found, return an empty list."""

        try:
            # Use model settings for non-o3 models
            settings = (
                None
                if self.model_name.startswith("o3")
                else OpenAIModelSettings(temperature=0.2, max_tokens=1000)
            )

            api_call_start = time.time()
            result = await self.agent.run(user_prompt, model_settings=settings)
            api_call_time = time.time() - api_call_start
            processing_time = time.time() - start_time

            # Ensure source_chunks is set correctly for all items
            action_items = result.output
            for item in action_items:
                if not item.source_chunks:
                    item.source_chunks = [chunk_id]

            logger.info(
                "Action item extraction completed",
                chunk_id=chunk_id,
                processing_time_ms=int(processing_time * 1000),
                api_call_time_ms=int(api_call_time * 1000),
                action_items_found=len(action_items),
                critical_items=sum(1 for item in action_items if item.is_critical),
                needs_review=sum(1 for item in action_items if item.needs_review),
                model=self.model_name,
            )

            return action_items

        except Exception as e:
            logger.error(
                "Action item extraction failed",
                chunk_id=chunk_id,
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
                model=self.model_name,
            )
            raise


class IntelligenceSynthesizer:
    """
    Aggregates chunk-level extractions into document-level intelligence.

    Responsibilities:
    - Deduplicate action items across chunks
    - Merge related summaries coherently
    - Generate executive summary (<500 chars)
    - Calculate aggregate confidence scores

    Expected behavior:
    - Handles 40+ chunk summaries efficiently
    - Preserves source chunk references
    - Creates hierarchical summary structure
    - Uses GPT-4 with temperature=0.5 for creativity
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-4"):
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key

        self.model_name = model
        self.agent = Agent(
            f"openai:{model}",
            output_type=IntelligenceResult,
            system_prompt=SYNTHESIS_PROMPT,
            retries=2,
        )

        logger.info(
            "IntelligenceSynthesizer initialized",
            model=model,
            supports_temperature=not model.startswith("o3"),
        )

    async def synthesize(self, extractions: list[dict]) -> IntelligenceResult:
        """
        Synthesize all chunk extractions into final intelligence.
        Input: List of {'summary': ChunkSummary, 'actions': List[ActionItem]}
        Output: Complete IntelligenceResult with all fields
        """
        start_time = time.time()

        # Aggregate all summaries and action items
        all_summaries = []
        all_actions = []
        all_speakers = set()

        for extraction in extractions:
            chunk_summary = extraction["summary"]
            chunk_actions = extraction["actions"]

            all_summaries.append(chunk_summary)
            all_actions.extend(chunk_actions)
            all_speakers.update(chunk_summary.speakers)

        logger.info(
            "Starting synthesis",
            total_chunks=len(extractions),
            total_summaries=len(all_summaries),
            total_actions=len(all_actions),
            unique_speakers=len(all_speakers),
            model=self.model_name,
        )

        # Create synthesis input
        synthesis_data = {
            "chunk_summaries": [
                {
                    "key_points": summary.key_points,
                    "decisions": summary.decisions,
                    "topics": summary.topics,
                    "speakers": summary.speakers,
                    "confidence": summary.confidence,
                }
                for summary in all_summaries
            ],
            "action_items": [
                {
                    "description": action.description,
                    "owner": action.owner,
                    "deadline": action.deadline,
                    "dependencies": action.dependencies,
                    "source_chunks": action.source_chunks,
                    "confidence": action.confidence,
                    "is_critical": action.is_critical,
                }
                for action in all_actions
            ],
            "metadata": {
                "total_chunks": len(extractions),
                "speakers": list(all_speakers),
                "avg_confidence": sum(s.confidence for s in all_summaries)
                / len(all_summaries)
                if all_summaries
                else 0.0,
            },
        }

        user_prompt = f"""Synthesize the following meeting intelligence data into a comprehensive result:

CHUNK SUMMARIES:
{synthesis_data['chunk_summaries']}

ACTION ITEMS:
{synthesis_data['action_items']}

METADATA:
{synthesis_data['metadata']}

Create:
1. Executive summary (<500 chars) - high-level overview
2. Detailed summary (<2000 chars) - comprehensive narrative
3. Bullet points (3-10) - key takeaways
4. Deduplicated action items - merge similar items, preserve source chunks
5. Key decisions - important choices made
6. Topics discussed - main subjects covered
7. Overall confidence score
8. Processing statistics"""

        try:
            # Use model settings for non-o3 models
            settings = (
                None
                if self.model_name.startswith("o3")
                else OpenAIModelSettings(temperature=0.5, max_tokens=2000)
            )

            api_call_start = time.time()
            result = await self.agent.run(user_prompt, model_settings=settings)
            api_call_time = time.time() - api_call_start
            processing_time = time.time() - start_time

            # Add processing stats to the result
            intelligence_result = result.output
            intelligence_result.processing_stats.update(
                {
                    "total_processing_time_ms": int(processing_time * 1000),
                    "api_call_time_ms": int(api_call_time * 1000),
                    "chunks_processed": len(extractions),
                    "original_action_items": len(all_actions),
                    "final_action_items": len(intelligence_result.action_items),
                    "deduplication_ratio": (
                        len(all_actions) - len(intelligence_result.action_items)
                    )
                    / len(all_actions)
                    if all_actions
                    else 0,
                    "speakers": list(all_speakers),
                    "model_used": self.model_name,
                }
            )

            logger.info(
                "Synthesis completed",
                processing_time_ms=int(processing_time * 1000),
                api_call_time_ms=int(api_call_time * 1000),
                final_confidence=intelligence_result.confidence_score,
                executive_summary_length=len(intelligence_result.executive_summary),
                detailed_summary_length=len(intelligence_result.detailed_summary),
                bullet_points_count=len(intelligence_result.bullet_points),
                final_action_items=len(intelligence_result.action_items),
                key_decisions_count=len(intelligence_result.key_decisions),
                topics_count=len(intelligence_result.topics_discussed),
                model=self.model_name,
            )

            return intelligence_result

        except Exception as e:
            logger.error(
                "Synthesis failed",
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
                model=self.model_name,
            )
            raise
