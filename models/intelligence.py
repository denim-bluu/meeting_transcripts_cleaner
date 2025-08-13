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
    - Enforce 1-5 key points per chunk
    - Validate confidence score range
    - Store speaker list from chunk
    
    Expected behavior:
    - Raises ValidationError if key_points empty or >5 items
    - Topics must have at least one entry
    - Confidence between 0.0 and 1.0
    """
    key_points: List[str] = Field(..., min_length=1, max_length=5)
    decisions: List[str] = Field(default_factory=list)
    topics: List[str] = Field(..., min_length=1)
    speakers: List[str] = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)


class IntelligenceResult(BaseModel):
    """
    Final synthesized intelligence output.
    
    Responsibilities:
    - Enforce executive summary length (<500 chars)
    - Validate all action items
    - Calculate overall confidence from components
    
    Expected behavior:
    - executive_summary truncated if >500 chars
    - bullet_points limited to 3-10 items
    - processing_stats includes timing and counts
    """
    executive_summary: str = Field(..., max_length=500)
    detailed_summary: str = Field(..., max_length=2000)
    bullet_points: List[str] = Field(..., min_length=3, max_length=10)
    action_items: List[ActionItem] = Field(default_factory=list)
    key_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    topics_discussed: List[str] = Field(..., min_length=1)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    processing_stats: Dict[str, Any] = Field(default_factory=dict)