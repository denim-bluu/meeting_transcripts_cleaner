"""AI agents for meeting intelligence extraction using Pydantic AI."""

import asyncio
import os
import time

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModelSettings
import structlog

from models.intelligence import (
    ActionItem,
    ChunkSummary,
    IntelligenceResult,
)

# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger(__name__)

# System prompts for intelligence extraction
SUMMARY_PROMPT = """You are an expert meeting transcriptionist specializing in Quote-First Extraction - identifying and preserving important explanations verbatim.

Your task: Identify and preserve important quotes/explanations from this meeting segment that should NOT be summarized.

QUOTE-FIRST EXTRACTION PRINCIPLES:
- PRESERVE technical explanations, process descriptions, and methodologies verbatim (or near-verbatim)
- IDENTIFY who said what - maintain speaker attribution
- CATEGORIZE quotes by type: technical_explanation, process_description, methodology, decision_rationale, key_insight
- AVOID summarizing or compressing important explanations
- FOCUS on preservation over compression

WHAT TO EXTRACT AS QUOTES:
✅ Technical process explanations: "Starmine evaluates analysts on their estimate accuracy—how close their forecasts are to actuals, how soon they converge, adjusted for stock volatility and estimate dispersion"
✅ Methodology descriptions: "The intrinsic valuation model uses discounted dividend approach with 15% cap in year 15 for non-dividend payers"
✅ System explanations: "Smart Estimates, a weighted consensus where more accurate analysts are weighted more heavily than less accurate ones"
✅ Decision rationales with context and numbers
✅ Key insights with specific data points

WHAT NOT TO EXTRACT AS QUOTES:
❌ Generic discussion: "We talked about the platform"
❌ Simple mentions: "CAM was discussed"
❌ Basic acknowledgments: "Everyone agreed"

EXAMPLE QUOTE EXTRACTION:
Speaker: "Joon Kang"
Quote: "Stardust was founded in 1998 in Arizona, based on the principle that sell-side analyst accuracy is measurable and persistent over time. The platform evaluates analysts on estimate accuracy—how close forecasts are to actuals and convergence speed, adjusted for stock volatility and estimate dispersion."
Context: "Company founding and core methodology explanation"
Type: "technical_explanation"

Return JSON with exactly these fields:
- "important_quotes": List of ImportantQuote objects with speaker, quote_text, context, quote_type
- "brief_context": Short paragraph (30-500 chars) providing minimal context between quotes - NOT detailed narrative
- "key_points": List of key points derived from quotes and discussion
- "technical_terms": Technical terms, methodologies, frameworks mentioned
- "decisions": Specific decisions with context and rationale
- "topics": Specific topics/technologies/methodologies discussed
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

SYNTHESIS_PROMPT = """You are an expert meeting intelligence synthesizer specializing in Quote-Based Synthesis - building comprehensive narratives around preserved quotes and technical explanations.

Your task: Synthesize all chunk-level quote extractions into comprehensive meeting intelligence that preserves verbatim technical content.

QUOTE-BASED SYNTHESIS PRINCIPLES:
- PRESERVE all important quotes verbatim from chunks
- BUILD narrative flow that connects preserved quotes seamlessly
- ORGANIZE quotes by topic/speaker for maximum coherence
- MAINTAIN exact technical language, names, numbers, and percentages from quotes
- CREATE comprehensive documentation that reads like detailed meeting notes
- AVOID compressing or summarizing technical explanations that were preserved as quotes

SYNTHESIS APPROACH:
1. COLLECT all important quotes from chunks
2. ORGANIZE quotes by theme/topic/chronology
3. BUILD detailed narrative that weaves quotes together naturally
4. PRESERVE technical explanations verbatim within the narrative
5. ADD minimal connective text to create flow between preserved content
6. ENSURE all specific names, methodologies, and numbers from quotes are maintained

EXAMPLE OF QUOTE-BASED SYNTHESIS:
"Nathaniel Meixler began with background on Starmine: 'Starmine was founded in 1998 in San Francisco, based on the principle that sell-side analyst accuracy is measurable and persistent over time. The platform evaluates analysts on estimate accuracy—how close forecasts are to actuals and convergence speed, adjusted for stock volatility and estimate dispersion.' He explained that 'these accuracy scores feed into Smart Estimates, a weighted consensus where more accurate analysts are weighted more heavily than less accurate ones.' The CAM methodology was detailed as 'a linear combination of factor models including Analyst Revisions, Price Momentum, Relative and Intrinsic Valuation, Earnings Quality, Smart Holdings, and Insider Filings.' When discussing performance, Meixler noted that 'when Predicted Surprise exceeds 2%, the model correctly predicts the direction of actual surprises 70% of the time.'"

AVOID COMPRESSION SYNTHESIS LIKE:
"The meeting covered Starmine's methodology and CAM components with performance metrics."

Return JSON with exactly these fields:
- "executive_summary": High-level overview connecting key quotes and outcomes (<800 chars)
- "detailed_summary": Comprehensive narrative built around preserved quotes (<8000 chars)
- "preserved_quotes": All important quotes from chunks, deduplicated and organized
- "technical_explanations": Quotes specifically about technical processes and methodologies
- "bullet_points": Key takeaways derived from quotes and preserved content (3-15)
- "action_items": Deduplicated list with preserved context
- "key_decisions": Decisions with context, rationale, and supporting quotes
- "topics_discussed": Specific topics/technologies/methodologies from quotes
- "participants_mentioned": All people and organizations mentioned
- "key_metrics": Important numbers, percentages, dates from preserved quotes
- "methodology_coverage": Technical methodologies discussed with relevant quotes
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

        user_prompt = f"""Apply Quote-First Extraction to this meeting segment:

Meeting segment:
{full_context}

Speakers in this segment: {', '.join(speakers)}

QUOTE-FIRST EXTRACTION INSTRUCTIONS:
1. IDENTIFY important explanations that should be preserved verbatim:
   - Technical process descriptions
   - Methodology explanations
   - System/platform explanations with specifics
   - Decision rationales with context
   - Key insights with data points

2. For each important explanation, create an ImportantQuote with:
   - speaker: Who said it
   - quote_text: Verbatim or near-verbatim preservation (minimum 20 chars)
   - context: What this explains/relates to
   - quote_type: technical_explanation, process_description, methodology, decision_rationale, or key_insight

3. PRESERVE technical terms, exact names, numbers, and percentages as spoken

4. Write brief_context (30-500 chars) to connect quotes - NOT detailed narrative

5. Extract supporting information: key points, technical terms, entities, quantitative data

FOCUS: Preserve important explanations verbatim rather than summarizing them."""

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

    def __init__(self, api_key: str | None = None, model: str = "gpt-4.1"):
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

    async def synthesize(
        self, extractions: list[dict[str, ChunkSummary | list[ActionItem]]]
    ) -> IntelligenceResult:
        """
        Synthesize all chunk extractions into final intelligence.
        Input: List of {'summary': ChunkSummary, 'actions': List[ActionItem]}
        Output: Complete IntelligenceResult with all fields
        """
        start_time = time.time()

        # Aggregate all summaries and action items
        all_summaries: list[ChunkSummary] = []
        all_actions: list[ActionItem] = []
        all_speakers = set()
        total_quotes = 0  # Initialize here

        for extraction in extractions:
            chunk_summary = extraction["summary"]
            if not isinstance(chunk_summary, ChunkSummary):
                raise ValueError("Invalid chunk summary")
            chunk_actions = extraction["actions"]
            if not isinstance(chunk_actions, list):
                raise ValueError("Invalid chunk actions")
            if not all(isinstance(action, ActionItem) for action in chunk_actions):
                raise ValueError("Invalid action item")

            all_summaries.append(chunk_summary)
            all_actions.extend(chunk_actions)
            all_speakers.update(chunk_summary.speakers)
            total_quotes += len(chunk_summary.important_quotes)  # Count quotes here

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
                    "important_quotes": [
                        {
                            "speaker": quote.speaker,
                            "quote_text": quote.quote_text,
                            "context": quote.context,
                            "quote_type": quote.quote_type,
                        }
                        for quote in summary.important_quotes
                    ],
                    "brief_context": summary.brief_context,
                    "key_points": summary.key_points,
                    "technical_terms": summary.technical_terms,
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

        # Log payload size for debugging
        payload_str = str(synthesis_data)
        payload_size = len(payload_str)
        logger.info(
            "Synthesis payload prepared",
            payload_size_chars=payload_size,
            estimated_tokens=payload_size // 4,
            total_quotes=total_quotes,
        )

        # Truncate if payload is too large (>50k chars ≈ 12.5k tokens)
        if payload_size > 50000:
            logger.warning(
                "Large synthesis payload detected, truncating for safety",
                original_size=payload_size,
                truncating_to=45000,
            )
            # Create truncated version of synthesis_data
            synthesis_data_truncated = (
                str(synthesis_data)[:45000] + "...[truncated for size]"
            )
            chunk_summaries_str = synthesis_data_truncated
        else:
            chunk_summaries_str = synthesis_data["chunk_summaries"]

        user_prompt = f"""Synthesize the following meeting intelligence data using Quote-Based Synthesis approach:

CHUNK SUMMARIES WITH IMPORTANT QUOTES:
{chunk_summaries_str}

ACTION ITEMS:
{synthesis_data['action_items']}

METADATA:
{synthesis_data['metadata']}

QUOTE-BASED SYNTHESIS INSTRUCTIONS:
1. EXTRACT all important quotes from chunk summaries
2. ORGANIZE quotes by theme, speaker, or chronological flow
3. BUILD comprehensive narrative that weaves quotes together seamlessly
4. PRESERVE all quotes verbatim - do not summarize technical explanations
5. CREATE detailed summary that reads like comprehensive meeting notes
6. SEPARATE quotes into technical_explanations vs general preserved_quotes
7. BUILD methodology_coverage mapping technical topics to relevant quotes
8. DEDUPLICATE similar quotes while preserving unique technical details
9. MAINTAIN exact speaker attribution for all quotes
10. CONNECT quotes with minimal narrative bridges, avoiding compression

CRITICAL: All technical explanations, process descriptions, and methodology quotes must be preserved verbatim in the detailed summary. Build narrative flow around these preserved quotes rather than compressing them."""

        try:
            # Use model settings for non-o3 models with increased timeout
            settings = (
                None
                if self.model_name.startswith("o3")
                else OpenAIModelSettings(temperature=0.5, max_tokens=3000, timeout=300)
            )

            api_call_start = time.time()

            # Add timeout wrapper for synthesis
            try:
                result = await asyncio.wait_for(
                    self.agent.run(user_prompt, model_settings=settings),
                    timeout=300,  # 5 minute timeout
                )
                api_call_time = time.time() - api_call_start
                processing_time = time.time() - start_time
            except asyncio.TimeoutError:
                logger.error(
                    "Synthesis timed out after 5 minutes",
                    chunks_processed=len(extractions),
                    model=self.model_name,
                )
                raise Exception(
                    "Synthesis timed out - try reducing chunk count or switching to faster model"
                )

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
                    "total_quotes_extracted": total_quotes,
                    "final_quotes_preserved": len(intelligence_result.preserved_quotes),
                    "technical_explanations_count": len(
                        intelligence_result.technical_explanations
                    ),
                    "avg_brief_context_length": sum(
                        len(s.brief_context) for s in all_summaries
                    )
                    / len(all_summaries)
                    if all_summaries
                    else 0,
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
