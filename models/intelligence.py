"""Pydantic models for meeting intelligence extraction."""

from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any


class ActionItem(BaseModel):
    """
    Represents single action item extracted from meeting.
    
    Responsibilities:
    - Validate description is meaningful (min 10 chars)
    - Auto-flag for review if confidence <0.8 or is_critical=True
    - Track source chunks for traceability
    
    Expected behavior:
    - needs_review automatically set based on confidence/criticality
    - Raises ValidationError if description too short
    - source_chunks must contain at least one chunk_id
    """
    description: str = Field(..., min_length=10, description="Action to be taken")
    owner: Optional[str] = Field(None, description="Person/team responsible")
    deadline: Optional[str] = Field(None, description="Due date if mentioned")
    dependencies: List[str] = Field(default_factory=list)
    source_chunks: List[int] = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_critical: bool = Field(default=False)
    needs_review: bool = Field(default=False)
    
    @model_validator(mode='after')
    def check_review_needed(self):
        # Auto-flag for review if low confidence or critical
        self.needs_review = self.confidence < 0.8 or self.is_critical
        return self


class ImportantQuote(BaseModel):
    """Represents an important quote or explanation that should be preserved verbatim."""
    speaker: str = Field(..., description="Who said this")
    quote_text: str = Field(..., min_length=20, description="Verbatim or near-verbatim quote")
    context: str = Field(..., description="What this quote explains or relates to")
    quote_type: str = Field(..., description="Type: 'technical_explanation', 'process_description', 'methodology', 'decision_rationale', 'key_insight'")

class ChunkSummary(BaseModel):
    """
    Quote-first extraction from single VTTChunk.
    
    Responsibilities:
    - Identify and preserve important explanations verbatim
    - Extract technical processes and methodologies as quotes
    - Capture key information with speaker attribution
    
    Expected behavior:
    - important_quotes preserve technical explanations verbatim
    - brief_context provides minimal narrative between quotes
    - Focus on preservation over summarization
    """
    important_quotes: List[ImportantQuote] = Field(default_factory=list,
                                                  description="Verbatim quotes of important explanations, processes, methodologies")
    brief_context: str = Field(..., min_length=30, max_length=500,
                              description="Minimal context to connect quotes, not detailed narrative")
    key_points: List[str] = Field(..., min_length=1, max_length=8,
                                  description="Key points derived from quotes and discussion")
    technical_terms: List[str] = Field(default_factory=list,
                                      description="Technical terms, methodologies, frameworks mentioned")
    decisions: List[str] = Field(default_factory=list,
                                description="Specific decisions with context and rationale")
    topics: List[str] = Field(..., min_length=1,
                             description="Specific topics/technologies/methodologies discussed")
    speakers: List[str] = Field(..., min_length=1)
    mentioned_entities: List[str] = Field(default_factory=list,
                                         description="Names of people, companies, products, technologies mentioned")
    quantitative_data: List[str] = Field(default_factory=list,
                                        description="Numbers, percentages, metrics, dates mentioned")
    confidence: float = Field(..., ge=0.0, le=1.0)


class IntelligenceResult(BaseModel):
    """
    Quote-based synthesized intelligence output.
    
    Responsibilities:
    - Preserve important quotes and build narrative around them
    - Organize quotes by type and topic
    - Create comprehensive meeting documentation
    - Calculate overall confidence from components
    
    Expected behavior:
    - preserved_quotes maintain verbatim technical explanations
    - detailed_summary builds narrative connecting quotes
    - Focus on enhancement of preserved content over compression
    """
    executive_summary: str = Field(..., max_length=800,
                                  description="High-level overview connecting key quotes and outcomes")
    detailed_summary: str = Field(..., max_length=8000,
                                 description="Comprehensive narrative built around preserved quotes, maintaining technical specificity")
    preserved_quotes: List[ImportantQuote] = Field(default_factory=list,
                                                  description="All important quotes preserved from chunks, organized by relevance")
    technical_explanations: List[ImportantQuote] = Field(default_factory=list,
                                                        description="Quotes specifically about technical processes and methodologies")
    bullet_points: List[str] = Field(..., min_length=3, max_length=15,
                                    description="Key takeaways derived from quotes and preserved content")
    action_items: List[ActionItem] = Field(default_factory=list)
    key_decisions: List[Dict[str, Any]] = Field(default_factory=list,
                                               description="Decisions with context, rationale, and supporting quotes")
    topics_discussed: List[str] = Field(..., min_length=1,
                                       description="Specific topics, technologies, and methodologies covered")
    participants_mentioned: List[str] = Field(default_factory=list,
                                             description="All people and organizations mentioned in the meeting")
    key_metrics: List[str] = Field(default_factory=list,
                                  description="Important numbers, percentages, dates, and quantitative data")
    methodology_coverage: Dict[str, List[str]] = Field(default_factory=dict,
                                                      description="Technical methodologies discussed with relevant quotes")
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    processing_stats: Dict[str, Any] = Field(default_factory=dict)