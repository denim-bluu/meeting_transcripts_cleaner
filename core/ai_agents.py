"""AI agents for transcript cleaning and review with enterprise-grade error handling."""

import json
import time
from typing import Dict, Optional

from openai import AsyncOpenAI
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from models.vtt import VTTChunk

logger = structlog.get_logger(__name__)


class TranscriptCleaner:
    """Clean transcript chunks using OpenAI API with model-specific parameter handling."""
    
    def __init__(self, api_key: str, model: str = "o3-mini"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        
        logger.info(
            "TranscriptCleaner initialized",
            model=model,
            supports_temperature=not model.startswith("o3"),
            supports_max_tokens=not model.startswith("o3")
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((Exception,))
    )
    async def clean_chunk(self, chunk: VTTChunk, prev_text: str = "") -> Dict:
        """
        Clean a single chunk with enterprise-grade error handling and structured output.
        
        Returns structured cleaning result with confidence scoring and change tracking.
        """
        start_time = time.time()
        context = prev_text[-200:] if prev_text else ""
        
        # Log detailed context for monitoring
        chunk_speakers = list(set(entry.speaker for entry in chunk.entries))
        chunk_text = chunk.to_transcript_text()
        
        logger.info(
            "Starting chunk cleaning",
            chunk_id=chunk.chunk_id,
            token_count=chunk.token_count,
            entries_count=len(chunk.entries),
            unique_speakers=len(chunk_speakers),
            speakers=chunk_speakers,
            text_length=len(chunk_text),
            context_length=len(context),
            model=self.model,
            text_preview=chunk_text[:100].replace('\n', ' ') + "..." if len(chunk_text) > 100 else chunk_text
        )
        
        # Enhanced prompt following Pydantic AI best practices
        system_prompt = """You are an expert transcript editor specializing in meeting transcripts. 

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

        user_prompt = f"""Previous context for flow: ...{context}

Current chunk to clean:
{chunk.to_transcript_text()}

Return JSON with cleaned_text, confidence, and changes_made."""

        try:
            logger.debug(
                "Starting chunk cleaning",
                chunk_id=chunk.chunk_id,
                token_count=chunk.token_count,
                model=self.model
            )
            
            # Prepare API call parameters (o3 models don't support temperature/max_completion_tokens)
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"}
            }
            
            # Add parameters only if not using o3 models
            if not self.model.startswith("o3"):
                api_params["temperature"] = 0.3  # Low temperature for consistent outputs
                api_params["max_tokens"] = 1000
            
            # Call OpenAI with structured output
            api_call_start = time.time()
            logger.debug(
                "Sending request to OpenAI API",
                chunk_id=chunk.chunk_id,
                model=self.model
            )
            
            response = await self.client.chat.completions.create(**api_params)
            
            api_call_time = time.time() - api_call_start
            logger.debug(
                "Received response from OpenAI API",
                chunk_id=chunk.chunk_id,
                api_call_time_ms=int(api_call_time * 1000),
                response_length=len(response.choices[0].message.content) if response.choices else 0,
                usage_tokens=response.usage.total_tokens if hasattr(response, 'usage') and response.usage else None
            )
            
            result = json.loads(response.choices[0].message.content)
            processing_time = time.time() - start_time
            
            # Validate and ensure required fields
            cleaned_result = {
                "cleaned_text": result.get("cleaned_text", chunk.to_transcript_text()),
                "confidence": float(result.get("confidence", 0.5)),
                "changes_made": result.get("changes_made", [])
            }
            
            # Enhanced success logging with quality metrics
            original_length = len(chunk_text)
            cleaned_length = len(cleaned_result["cleaned_text"])
            length_change_pct = ((cleaned_length - original_length) / original_length * 100) if original_length > 0 else 0
            
            logger.info(
                "Chunk cleaning completed successfully",
                chunk_id=chunk.chunk_id,
                processing_time_ms=int(processing_time * 1000),
                api_call_time_ms=int(api_call_time * 1000),
                confidence=cleaned_result["confidence"],
                changes_count=len(cleaned_result["changes_made"]),
                changes_made=cleaned_result["changes_made"][:3],  # First 3 changes for monitoring
                text_metrics={
                    "original_length": original_length,
                    "cleaned_length": cleaned_length,
                    "length_change_pct": round(length_change_pct, 1),
                    "compression_ratio": round(cleaned_length / original_length, 3) if original_length > 0 else 1.0
                },
                model=self.model,
                usage_tokens=response.usage.total_tokens if hasattr(response, 'usage') and response.usage else None
            )
            
            return cleaned_result
            
        except json.JSONDecodeError as e:
            logger.error(
                "JSON parsing failed in chunk cleaning",
                chunk_id=chunk.chunk_id,
                error=str(e),
                model=self.model
            )
            raise
            
        except Exception as e:
            logger.error(
                "Chunk cleaning failed",
                chunk_id=chunk.chunk_id,
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
                model=self.model
            )
            raise


class TranscriptReviewer:
    """Review cleaned transcripts for quality."""
    
    def __init__(self, api_key: str, model: str = "o3-mini"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((Exception,))
    )
    async def review_chunk(self, original: VTTChunk, cleaned: str) -> Dict:
        """
        Review cleaned text quality with comprehensive evaluation criteria.
        
        Returns structured review result with detailed quality assessment.
        """
        start_time = time.time()
        
        # Enhanced system prompt with specific evaluation criteria
        system_prompt = """You are an expert transcript quality reviewer with deep expertise in meeting transcription standards.

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

        user_prompt = f"""Original transcript:
{original.to_transcript_text()}

Cleaned version:
{cleaned}

Evaluate the cleaning quality and return JSON with quality_score, issues, and accept."""

        try:
            logger.debug(
                "Starting chunk review",
                chunk_id=original.chunk_id,
                original_length=len(original.to_transcript_text()),
                cleaned_length=len(cleaned),
                model=self.model
            )
            
            # Prepare API call parameters (o3 models don't support temperature/max_completion_tokens)
            api_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"}
            }
            
            # Add parameters only if not using o3 models
            if not self.model.startswith("o3"):
                api_params["temperature"] = 0.2  # Very low temperature for consistent quality evaluation
                api_params["max_tokens"] = 500
            
            # Call OpenAI with structured output
            response = await self.client.chat.completions.create(**api_params)
            
            result = json.loads(response.choices[0].message.content)
            processing_time = time.time() - start_time
            
            # Validate and ensure required fields
            quality_score = float(result.get("quality_score", 0.5))
            review_result = {
                "quality_score": quality_score,
                "issues": result.get("issues", []),
                "accept": quality_score >= 0.7  # Accept if quality score >= 0.7
            }
            
            logger.info(
                "Chunk review completed",
                chunk_id=original.chunk_id,
                processing_time_ms=int(processing_time * 1000),
                quality_score=quality_score,
                issues_count=len(review_result["issues"]),
                accepted=review_result["accept"],
                model=self.model
            )
            
            return review_result
            
        except json.JSONDecodeError as e:
            logger.error(
                "JSON parsing failed in chunk review",
                chunk_id=original.chunk_id,
                error=str(e),
                model=self.model
            )
            raise
            
        except Exception as e:
            logger.error(
                "Chunk review failed",
                chunk_id=original.chunk_id,
                error=str(e),
                processing_time_ms=int((time.time() - start_time) * 1000),
                model=self.model
            )
            raise