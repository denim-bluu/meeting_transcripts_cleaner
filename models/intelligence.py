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


class ChunkSummary(BaseModel):
    """
    Summary extracted from single VTTChunk.
    
    Responsibilities:
    - Extract detailed narrative with specifics
    - Capture key points with rich context
    - Store speaker list from chunk
    
    Expected behavior:
    - Detailed narrative captures names, numbers, methodologies
    - Key points include specific details not just abstractions
    - Confidence between 0.0 and 1.0
    """
    detailed_narrative: str = Field(..., min_length=50, max_length=1000, 
                                   description="Rich paragraph describing what was discussed with names, numbers, and specifics")
    key_points: List[str] = Field(..., min_length=1, max_length=8,
                                  description="Detailed points with specific information, not generic statements")
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
    Final synthesized intelligence output.
    
    Responsibilities:
    - Create comprehensive executive summary
    - Provide detailed narrative with full context
    - Validate all action items
    - Calculate overall confidence from components
    
    Expected behavior:
    - executive_summary provides high-level overview
    - detailed_summary contains rich narrative with specifics
    - processing_stats includes timing and counts
    """
    executive_summary: str = Field(..., max_length=800,
                                  description="High-level overview of the meeting's purpose and outcomes")
    detailed_summary: str = Field(..., max_length=5000,
                                 description="Comprehensive narrative with names, numbers, methodologies, and specific details")
    bullet_points: List[str] = Field(..., min_length=3, max_length=15,
                                    description="Key takeaways with specific details, not generic statements")
    action_items: List[ActionItem] = Field(default_factory=list)
    key_decisions: List[Dict[str, Any]] = Field(default_factory=list,
                                               description="Decisions with context, rationale, and implications")
    topics_discussed: List[str] = Field(..., min_length=1,
                                       description="Specific topics, technologies, and methodologies covered")
    participants_mentioned: List[str] = Field(default_factory=list,
                                             description="All people and organizations mentioned in the meeting")
    key_metrics: List[str] = Field(default_factory=list,
                                  description="Important numbers, percentages, dates, and quantitative data")
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    processing_stats: Dict[str, Any] = Field(default_factory=dict)