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
SUMMARY_PROMPT = """You are an expert meeting analyst specializing in extracting detailed, specific information from meeting segments.

Your task: Extract comprehensive information from this meeting segment with rich details.

CRITICAL INSTRUCTIONS:
- Capture SPECIFIC names, numbers, percentages, dates, and methodologies
- Include technical terms, company names, product names exactly as mentioned
- Extract quantitative data (percentages, amounts, timeframes, metrics)
- Record key entities (people, organizations, technologies, products)
- Write detailed narratives, not generic summaries
- Preserve context and relationships between concepts

EXAMPLE OF GOOD OUTPUT:
- "Nathaniel Meixler explained that Starmine was founded in 1998 in San Francisco, based on the principle that sell-side analyst accuracy is measurable and persistent over time"
- "The CAM score uses Smart Estimates with 70% accuracy when Predicted Surprise exceeds 2%"
- "Intrinsic valuation model uses discounted dividend approach with 15% cap in year 15 for non-dividend payers"

EXAMPLE OF BAD OUTPUT (too generic):
- "Discussed platform overview"
- "Talked about scoring methodology" 
- "Reviewed model performance"

Return JSON with exactly these fields:
- "detailed_narrative": Rich paragraph (50-1000 chars) with specific names, numbers, and methodologies
- "key_points": List of 1-8 detailed points with specifics, not abstractions
- "decisions": Specific decisions with context and rationale
- "topics": Specific topics/technologies/methodologies (not just "platform" or "model")
- "speakers": List of speakers in this segment
- "mentioned_entities": Names of people, companies, products, technologies mentioned
- "quantitative_data": Numbers, percentages, metrics, dates mentioned
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

SYNTHESIS_PROMPT = """You are an expert meeting intelligence synthesizer specializing in creating comprehensive, detailed meeting summaries with rich context.

Your task: Synthesize all chunk-level extractions into cohesive, detailed meeting intelligence that preserves specificity.

CRITICAL SYNTHESIS PRINCIPLES:
- PRESERVE all specific names, numbers, percentages, dates, and technical details
- Create narrative flow that connects concepts and maintains context
- Avoid generic language - keep technical terms and methodologies intact
- Maintain the richness of detail from chunk summaries
- Connect related concepts across different parts of the meeting
- Preserve quantitative data and metrics exactly as discussed

EXAMPLE OF GOOD SYNTHESIS:
"Nathaniel Meixler provided a comprehensive overview of Starmine, founded in 1998 in San Francisco, explaining that their foundational insight is that sell-side analyst accuracy is measurable and persistent over time. The platform evaluates analysts on estimate accuracy—how close forecasts are to actuals and convergence speed, adjusted for stock volatility and estimate dispersion. These accuracy scores feed into Smart Estimates, a weighted consensus where more accurate analysts receive higher weighting. The CAM (Combined Alpha Model) is a linear combination of factor models including Analyst Revisions (ARM), Price Momentum, Relative and Intrinsic Valuation, Earnings Quality, Smart Holdings, and Insider Filings. When Predicted Surprise exceeds 2%, the model correctly predicts the direction of actual surprises 70% of the time."

AVOID GENERIC SYNTHESIS LIKE:
"The meeting covered platform capabilities and discussed various models and methodologies."

Process:
1. Merge narratives while preserving ALL specific details
2. Deduplicate action items but maintain context
3. Create executive summary (up to 800 characters) with key specifics
4. Generate detailed summary (up to 5000 characters) with comprehensive narrative
5. Preserve all quantitative data and entity mentions
6. Calculate overall confidence score

Return JSON with exactly these fields:
- "executive_summary": High-level overview with key specifics (<800 chars)
- "detailed_summary": Comprehensive narrative with names, numbers, methodologies (<5000 chars)
- "bullet_points": List of 3-15 key takeaways with specific details
- "action_items": Deduplicated list with preserved context
- "key_decisions": Decisions with context, rationale, and implications
- "topics_discussed": Specific topics/technologies/methodologies (not generic terms)
- "participants_mentioned": All people and organizations mentioned
- "key_metrics": Important numbers, percentages, dates, quantitative data
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
    - Uses o3-mini with temperature=0.3 for consistency
    - Logs all extractions with timing metrics
    - Raises on API errors after 3 retries
    """

    def __init__(self, api_key: str | None = None, model: str = "o3-mini"):
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

        user_prompt = f"""Analyze this meeting segment and extract detailed, specific information:

Meeting segment:
{full_context}

Speakers in this segment: {', '.join(speakers)}

EXTRACT WITH SPECIFICITY:
1. Write a detailed narrative paragraph (50-1000 chars) that captures names, numbers, percentages, dates, and methodologies mentioned
2. List key points with specific details - avoid generic statements like "discussed models" 
3. Identify any decisions with context and rationale
4. List specific topics/technologies/methodologies (not just "platform" or "discussion")
5. Extract all mentioned entities (people, companies, products, technologies)
6. Capture quantitative data (numbers, percentages, metrics, dates)
7. Assess your confidence in the extraction quality

Remember: Preserve technical terms, exact names, and specific numbers exactly as mentioned."""

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
    - Uses o3-mini with temperature=0.2 for precision
    - Validates each item before returning
    """

    def __init__(self, api_key: str | None = None, model: str = "o3-mini"):
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
    - Uses o3-mini with temperature=0.5 for creativity
    """

    def __init__(self, api_key: str | None = None, model: str = "o3-mini"):
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
                    "detailed_narrative": summary.detailed_narrative,
                    "key_points": summary.key_points,
                    "decisions": summary.decisions,
                    "topics": summary.topics,
                    "speakers": summary.speakers,
                    "mentioned_entities": summary.mentioned_entities,
                    "quantitative_data": summary.quantitative_data,
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

        user_prompt = f"""Synthesize the following meeting intelligence data into a comprehensive, detailed result that preserves specificity:

CHUNK SUMMARIES WITH DETAILED NARRATIVES:
{synthesis_data['chunk_summaries']}

ACTION ITEMS:
{synthesis_data['action_items']}

METADATA:
{synthesis_data['metadata']}

SYNTHESIS REQUIREMENTS:
1. Executive summary (<800 chars) - overview with key names, numbers, and outcomes
2. Detailed summary (<5000 chars) - comprehensive narrative preserving ALL specific details, names, percentages, methodologies, and technical terms
3. Bullet points (3-15) - key takeaways with specific information, not generic statements
4. Deduplicated action items - merge similar items while preserving context and source chunks
5. Key decisions - specific choices with context, rationale, and implications  
6. Topics discussed - specific technologies/methodologies/concepts (avoid generic terms)
7. Participants mentioned - all people and organizations referenced
8. Key metrics - important numbers, percentages, dates, quantitative data
9. Overall confidence score
10. Processing statistics

CRITICAL: Preserve all specific names, numbers, percentages, dates, and technical details from the chunk summaries. Create narrative flow while maintaining specificity."""

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
            
            # Collect all entities and metrics from chunk summaries
            all_entities = set()
            all_metrics = set()
            for summary in all_summaries:
                all_entities.update(summary.mentioned_entities)
                all_metrics.update(summary.quantitative_data)
            
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
                    "unique_entities_extracted": len(all_entities),
                    "quantitative_data_points": len(all_metrics),
                    "avg_narrative_length": sum(len(s.detailed_narrative) for s in all_summaries) / len(all_summaries) if all_summaries else 0,
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
