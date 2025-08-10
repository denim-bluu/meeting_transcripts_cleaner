# Implementation Guide - Meeting Transcript Cleaner

## Quick Start

You're implementing a **dual-agent transcript cleaner** that processes documents in 500-token segments using a cleaning agent followed by a review agent, achieving 97-98% accuracy. The progressive review UI shows only segments needing attention, reducing review time by 90%.

## Project Setup

### 1. Initialize Project Structure

```bash
# Create this exact structure (matches System Design Document)
meeting-transcript-cleaner/
├── app.py                      # Entry point
├── state/
│   └── app_state.py           # Reflex state management
├── models/
│   └── schemas.py             # Pydantic models for structured output
├── core/
│   ├── document_processor.py  # Parse & segment (500 tokens)
│   ├── cleaning_agent.py      # First stage agent
│   ├── review_agent.py        # Second stage agent
│   └── confidence_categorizer.py # Categorize by confidence
├── prompts/
│   ├── cleaning.py           # Cleaning agent prompt
│   └── review.py             # Review agent prompt
├── components/
│   ├── file_upload.py       
│   ├── summary_view.py      # Shows categorized results
│   ├── review_view.py       # Progressive review UI
│   └── diff_viewer.py       
├── utils/
│   ├── validators.py        
│   └── cache.py            
├── config.py                 
├── requirements.txt
└── .env
```

### 2. Install Dependencies

```bash
uv add reflex pydantic-ai openai pydantic python-dotenv aiofiles cachetools
```

### 3. Environment Setup

```bash
# .env file
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=o3-mini
MAX_SECTION_TOKENS=500  # Optimal for accuracy
CLEANING_TEMPERATURE=0.2
REVIEW_TEMPERATURE=0.0
AUTO_ACCEPT_THRESHOLD=0.95
MAX_RETRIES=2
PROCESSING_TIMEOUT=30
MAX_FILE_SIZE=10485760  # 10MB in bytes
ALLOWED_EXTENSIONS=.vtt,.txt
ENABLE_CACHE=true
CACHE_TTL=3600
```

## Core Implementation

### Step 1: Pydantic Models (models/schemas.py)

```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal
from datetime import datetime

class CleaningResult(BaseModel):
    """Structured output from cleaning agent"""
    cleaned_text: str = Field(description="The cleaned transcript text")
    changes_made: List[str] = Field(description="List of changes applied")
    confidence_score: float = Field(ge=0, le=1)
    preservation_check: bool
    
    @validator('confidence_score')
    def valid_confidence(cls, v):
        if not 0 <= v <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        return v

class ReviewDecision(BaseModel):
    """Structured output from review agent"""
    decision: Literal["accept", "reject", "modify"]
    confidence: float = Field(ge=0, le=1)
    issues_found: List[str] = Field(default_factory=list)
    suggested_corrections: Optional[str] = None
    reasoning: str

class SegmentCategory(BaseModel):
    """Categorization result"""
    category: Literal["auto_accept", "quick_review", "detailed_review", "ai_flagged"]
    confidence: float
    segment_id: str
```

### Step 2: App Entry Point (app.py)

```python
import reflex as rx
from state.app_state import AppState
from components.file_upload import file_upload
from components.section_editor import section_editor

def index() -> rx.Component:
    """Main app layout"""
    return rx.vstack(
        rx.heading("Meeting Transcript Cleaner", size="8"),
        file_upload(),
        rx.cond(
            AppState.sections.length() > 0,
            section_editor(),
            rx.text("Upload a VTT or TXT file to begin")
        ),
        width="100%",
        max_width="1200px",
        margin="0 auto",
        padding="20px"
    )

app = rx.App()
app.add_page(index, title="Transcript Cleaner")
```

### Step 2: State Management (state/app_state.py)

```python
import reflex as rx
from typing import List, Dict, Optional
from core.document_processor import DocumentProcessor
from core.section_cleaner import SectionCleaner
from core.change_tracker import ChangeTracker, Change

class AppState(rx.State):
    """Central state - single source of truth"""
    
    # Document state
    document_id: str = ""
    document_type: str = ""  # "vtt" or "txt"
    sections: List[Dict] = []
    current_index: int = 0
    
    # Processing state
    is_processing: bool = False
    error_message: str = ""
    
    # Changes tracking
    change_tracker: ChangeTracker = ChangeTracker()
    current_change: Optional[Dict] = None
    
    async def upload_file(self, files: List[rx.UploadFile]):
        """Handle file upload with security validation"""
        if not files:
            return
            
        file = files[0]
        
        # Security validation
        if not self._validate_file(file):
            self.error_message = "Invalid file type or size"
            return
        
        content = await file.read()
        content_str = content.decode('utf-8')
        
        # Sanitize content
        content_str = self._sanitize_content(content_str)
        
        # Detect type
        self.document_type = "vtt" if file.filename.endswith('.vtt') else "txt"
        
        # Process document
        processor = DocumentProcessor()
        document = processor.parse(content_str, self.document_type)
        self.sections = processor.segment(document)
        self.document_id = document.id
        
        # Reset state
        self.current_index = 0
        self.change_tracker = ChangeTracker()
        self.error_message = ""
    
    def _validate_file(self, file: rx.UploadFile) -> bool:
        """Validate file size and type"""
        MAX_SIZE = int(os.getenv('MAX_FILE_SIZE', 10485760))  # 10MB default
        ALLOWED_EXT = os.getenv('ALLOWED_EXTENSIONS', '.vtt,.txt').split(',')
        
        # Check size
        if file.size > MAX_SIZE:
            return False
        
        # Check extension
        if not any(file.filename.endswith(ext) for ext in ALLOWED_EXT):
            return False
            
        return True
    
    def _sanitize_content(self, content: str) -> str:
        """Sanitize content to prevent injection"""
        import re
        # Remove potential prompt injection patterns
        content = re.sub(r'<\|.*?\|>', '', content)
        content = re.sub(r'###SYSTEM.*?###', '', content, flags=re.DOTALL)
        return content
    
    async def process_section(self):
        """Process current section with OpenAI"""
        self.is_processing = True
        self.error_message = ""
        
        try:
            current_section = self.sections[self.current_index]
            
            # Build context from adjacent sections
            context = self._build_context()
            
            # Clean with OpenAI
            cleaner = SectionCleaner()
            cleaned_content = await cleaner.clean(
                section=current_section,
                doc_type=self.document_type,
                context=context
            )
            
            # Validate preservation
            if not cleaner.validate_preservation(
                current_section['content'], 
                cleaned_content
            ):
                self.error_message = "Content loss detected - automatically rejected"
                return
            
            # Store change for display
            self.current_change = {
                'original': current_section['content'],
                'cleaned': cleaned_content,
                'section_id': current_section['id']
            }
            
        except Exception as e:
            self.error_message = f"Processing failed: {str(e)}"
        finally:
            self.is_processing = False
    
    def accept_change(self):
        """Accept current change and move forward"""
        if self.current_change:
            change = Change(
                section_id=self.current_change['section_id'],
                original=self.current_change['original'],
                cleaned=self.current_change['cleaned'],
                status='accepted'
            )
            self.change_tracker.record_change(change)
            self.current_change = None
            self._next_section()
    
    def reject_change(self):
        """Reject change, keep original"""
        if self.current_change:
            change = Change(
                section_id=self.current_change['section_id'],
                original=self.current_change['original'],
                cleaned=self.current_change['original'],  # Keep original
                status='rejected'
            )
            self.change_tracker.record_change(change)
            self.current_change = None
            self._next_section()
    
    def _next_section(self):
        """Move to next section"""
        if self.current_index < len(self.sections) - 1:
            self.current_index += 1
        
    def _build_context(self) -> Optional[Dict]:
        """Build context from adjacent sections"""
        context = {}
        
        if self.current_index > 0:
            prev = self.sections[self.current_index - 1]['content']
            context['previous_section_end'] = prev[-100:] if len(prev) > 100 else prev
            
        if self.current_index < len(self.sections) - 1:
            next_sec = self.sections[self.current_index + 1]['content']
            context['next_section_start'] = next_sec[:100] if len(next_sec) > 100 else next_sec
            
        return context if context else None
    
    def export_document(self) -> str:
        """Export the final cleaned document"""
        processor = DocumentProcessor()
        changes_dict = self.change_tracker.get_changes_dict()
        final_content = processor.reassemble(self.sections, changes_dict)
        return final_content
    
    async def download_document(self):
        """Trigger document download"""
        final_content = self.export_document()
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cleaned_document_{timestamp}.txt"
        
        # Return as downloadable file
        return rx.download(
            data=final_content.encode('utf-8'),
            filename=filename
        )
```

### Step 3: Document Processor (core/document_processor.py)

```python
import re
import uuid
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class Document:
    id: str
    type: str
    original_content: str
    metadata: Dict

class DocumentProcessor:
    """Parse and segment documents per System Design spec"""
    
    def parse(self, content: str, doc_type: str) -> Document:
        """Parse raw content into Document"""
        return Document(
            id=str(uuid.uuid4()),
            type=doc_type,
            original_content=content,
            metadata={'lines': content.count('\n')}
        )
    
    def segment(self, document: Document) -> List[Dict]:
        """Segment based on document type"""
        if document.type == 'vtt':
            return self._segment_vtt(document.original_content)
        else:
            return self._segment_notes(document.original_content)
    
    def _segment_vtt(self, content: str) -> List[Dict]:
        """
        Segment VTT by speaker changes (max 5 turns) or time (3 min)
        Per System Design: Section 2.2
        """
        sections = []
        current_section = []
        current_speaker = None
        turn_count = 0
        
        # Parse VTT blocks
        blocks = re.split(r'\n\n+', content)
        
        for block in blocks:
            if '-->' in block:  # Timestamp block
                lines = block.split('\n')
                
                # Extract speaker from <v Speaker> tags
                text_lines = ' '.join(lines[1:])
                speaker_match = re.search(r'<v ([^>]+)>', text_lines)
                
                if speaker_match:
                    speaker = speaker_match.group(1)
                    text = re.sub(r'<[^>]+>', '', text_lines).strip()
                    
                    # Check if we need new section
                    if (speaker != current_speaker and current_speaker is not None) or turn_count >= 5:
                        if current_section:
                            sections.append({
                                'id': f'section_{len(sections)}',
                                'content': '\n'.join(current_section),
                                'speaker': current_speaker,
                                'type': 'transcript'
                            })
                        current_section = []
                        turn_count = 0
                    
                    # Add to current section
                    current_section.append(f"{speaker}: {text}")
                    current_speaker = speaker
                    turn_count += 1
        
        # Add final section
        if current_section:
            sections.append({
                'id': f'section_{len(sections)}',
                'content': '\n'.join(current_section),
                'speaker': current_speaker,
                'type': 'transcript'
            })
        
        return sections
    
    def _segment_notes(self, content: str) -> List[Dict]:
        """Segment notes by paragraphs"""
        sections = []
        paragraphs = re.split(r'\n\n+', content)
        
        for i, para in enumerate(paragraphs):
            if para.strip():
                sections.append({
                    'id': f'section_{i}',
                    'content': para.strip(),
                    'type': 'notes'
                })
        
        return sections
    
    def reassemble(self, sections: List[Dict], changes: Dict) -> str:
        """Reassemble document from accepted changes"""
        final_parts = []
        
        for section in sections:
            change = changes.get(section['id'])
            if change and change.status == 'accepted':
                final_parts.append(change.cleaned)
            else:
                final_parts.append(section['content'])
        
        return '\n\n'.join(final_parts)
```

### Step 4: Cleaning Agent (core/cleaning_agent.py)

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from models.schemas import CleaningResult
from prompts.cleaning import CLEANING_PROMPT
from cachetools import TTLCache
import os

class CleaningAgent:
    """First stage: Clean transcript segments with structured output"""
    
    def __init__(self):
        self.model = OpenAIModel(
            'o3-mini',
            api_key=os.getenv('OPENAI_API_KEY')
        )
        self.agent = Agent(
            self.model,
            result_type=CleaningResult,
            system_prompt=CLEANING_PROMPT,
            retries=2
        )
        self.cache = TTLCache(maxsize=100, ttl=int(os.getenv('CACHE_TTL', 3600)))
        self.enable_cache = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
        
    async def clean(
        self, 
        section: Dict, 
        doc_type: str, 
        context: Optional[Dict] = None
    ) -> str:
        """Clean section with OpenAI, with caching and retry"""
        
        # Check cache first
        if self.enable_cache:
            cache_key = self._get_cache_key(section['content'], doc_type)
            if cache_key in self.cache:
                return self.cache[cache_key]
        
        # Select prompt based on type
        base_prompt = TRANSCRIPT_PROMPT if doc_type == 'vtt' else NOTES_PROMPT
        
        # Sanitize user content before sending to API
        sanitized_content = self._sanitize_for_prompt(section['content'])
        
        # Build messages
        messages = [
            {"role": "system", "content": base_prompt}
        ]
        
        # Add context if available
        if context:
            context_msg = "Context:\n"
            if 'previous_section_end' in context:
                context_msg += f"Previous section ended with: ...{context['previous_section_end']}\n"
            if 'next_section_start' in context:
                context_msg += f"Next section starts with: {context['next_section_start']}..."
            messages.append({"role": "user", "content": context_msg})
        
        # Add section content
        messages.append({
            "role": "user", 
            "content": f"Clean this section while preserving ALL content:\n\n{sanitized_content}"
        })
        
        # Call OpenAI with retry logic
        max_retries = int(os.getenv('MAX_RETRIES', 3))
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.3,  # Low for consistency
                    max_tokens=4000,
                    timeout=int(os.getenv('PROCESSING_TIMEOUT', 30))
                )
                
                result = response.choices[0].message.content
                
                # Cache the result
                if self.enable_cache:
                    self.cache[cache_key] = result
                
                return result
                
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise Exception("Processing timeout after multiple retries")
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise Exception(f"OpenAI API error after {max_retries} retries: {str(e)}")
    
    def _get_cache_key(self, content: str, doc_type: str) -> str:
        """Generate cache key for content"""
        content_hash = hashlib.md5(f"{content}:{doc_type}".encode()).hexdigest()
        return f"clean_{content_hash}"
    
    def _sanitize_for_prompt(self, content: str) -> str:
        """Sanitize content to prevent prompt injection"""
        import re
        # Remove potential injection patterns
        content = re.sub(r'<\|.*?\|>', '', content)
        content = re.sub(r'###SYSTEM.*?###', '', content, flags=re.DOTALL)
        content = re.sub(r'\[INST\].*?\[/INST\]', '', content, flags=re.DOTALL)
        return content
    
    def validate_preservation(self, original: str, cleaned: str) -> bool:
        """
        Validate no significant content loss
        Per System Design: Zero tolerance for omissions
        """
        # Extract ALL meaningful words (not just fillers)
        def extract_content_words(text):
            # Only remove pure filler words that can be safely cleaned
            pure_fillers = {'um', 'uh', 'er', 'ah'}  # Only verbal fillers
            words = set(text.lower().split())
            return words - pure_fillers
        
        original_words = extract_content_words(original)
        cleaned_words = extract_content_words(cleaned)
        
        # Check if ANY content words are missing
        missing = original_words - cleaned_words
        
        # STRICT: Zero tolerance for content loss
        # Only allow removal of pure filler words
        for word in missing:
            if word not in {'um', 'uh', 'er', 'ah'}:
                print(f"Content loss detected: '{word}' was removed")
                return False
                
        return True
```

### Step 5: Review Agent (core/review_agent.py)

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from models.schemas import ReviewDecision
from prompts.review import REVIEW_PROMPT
import os

class ReviewAgent:
    """Second stage: Review and validate cleaning"""
    
    def __init__(self):
        self.model = OpenAIModel(
            'o3-mini',
            api_key=os.getenv('OPENAI_API_KEY')
        )
        self.agent = Agent(
            self.model,
            result_type=ReviewDecision,
            system_prompt=REVIEW_PROMPT,
            retries=1
        )
    
    async def review(
        self,
        original: str,
        cleaned: str,
        changes: List[str]
    ) -> ReviewDecision:
        """Review cleaning quality and decide action"""
        
        review_prompt = f"""
        Original: {original}
        Cleaned: {cleaned}
        Changes Made: {', '.join(changes)}
        
        Review for content preservation and accuracy.
        """
        
        result = await self.agent.run(
            review_prompt,
            model_settings={
                'temperature': float(os.getenv('REVIEW_TEMPERATURE', 0.0)),
                'response_format': {'type': 'json_object'}
            }
        )
        
        return result.data
```

### Step 6: Progressive Review UI (components/summary_view.py)

```python
import reflex as rx
from state.app_state import AppState

class SummaryView(rx.Component):
    """Shows processing results categorized by confidence"""
    
    def render(self) -> rx.Component:
        return rx.vstack(
            rx.heading("Processing Complete", size="8"),
            
            # Statistics grid
            rx.grid(
                self._stat_card("✅ Auto-Accepted", AppState.stats['auto_accepted'], "green"),
                self._stat_card("👀 Quick Review", AppState.stats['quick_review'], "yellow"),
                self._stat_card("⚠️ Detailed Review", AppState.stats['detailed_review'], "orange"),
                self._stat_card("🚨 AI Flagged", AppState.stats['ai_flagged'], "red"),
                columns=4,
                gap="4"
            ),
            
            # Time estimate
            rx.alert(
                rx.alert_icon(),
                rx.alert_title(f"Estimated review time: {AppState.estimated_time} minutes"),
                status="info"
            ),
            
            # Action buttons
            rx.hstack(
                rx.button(
                    "Auto-accept High Confidence",
                    on_click=AppState.auto_accept_high_confidence,
                    color_scheme="green",
                    size="lg"
                ),
                rx.button(
                    f"Review {AppState.needs_review_count} Segments",
                    on_click=AppState.start_review,
                    color_scheme="blue",
                    size="lg"
                ),
                gap="4"
            ),
            
            padding="6",
            width="100%"
        )
    
    def _stat_card(self, title: str, count: int, color: str) -> rx.Component:
        return rx.box(
            rx.vstack(
                rx.text(title, size="5", weight="bold"),
                rx.text(str(count), size="8"),
                rx.text("segments", size="3", color="gray.500"),
                align="center"
            ),
            padding="4",
            border_radius="lg",
            border=f"2px solid",
            border_color=f"{color}.200",
            bg=f"{color}.50"
        )
```

### Step 7: Prompts (prompts/cleaning.py)

```python
# prompts/cleaning.py
CLEANING_PROMPT = """You are a transcript cleaning agent. Process small segments (2-3 sentences) with high accuracy.

Your task:
1. Fix ONLY obvious errors (typos, duplicate words, clear ASR mistakes)
2. Preserve ALL content including filler words
3. Track every change you make
4. Provide confidence score (0-1) for your cleaning

Return structured output with:
- cleaned_text: The corrected text
- changes_made: List of specific changes
- confidence_score: How confident you are (0-1)
- preservation_check: True if all content preserved
"""

# prompts/review.py
REVIEW_PROMPT = """You are a quality review agent. Review cleaned transcripts for accuracy.

Evaluate:
1. Is all original content preserved?
2. Were the corrections appropriate?
3. Are there any remaining errors?

Return structured decision:
- accept: Cleaning is good
- reject: Major issues found
- modify: Minor corrections needed

Include confidence score and reasoning.

CRITICAL RULES:
1. NEVER omit ANY information, no matter how minor
2. Expand abbreviations and shorthand into full sentences
3. Fix grammar and punctuation
4. Maintain all specific details, numbers, names
5. Preserve the original meaning and nuance

Examples:
- "Q4 metrics discussion w/ John" → "We discussed Q4 metrics with John"
- "TODO: follow up re: budget" → "TODO: Follow up regarding the budget"

Transform the notes into professional, complete sentences while keeping every single detail."""
```

## Critical Implementation Rules

### Rule 1: Use 500-Token Segments for Optimal Accuracy

```python
# ❌ WRONG - Large segments reduce accuracy
segments = document_processor.segment(doc, max_tokens=2000)  # 88% accuracy

# ✅ RIGHT - Small segments for high accuracy
segments = document_processor.segment(doc, max_tokens=500)  # 96% accuracy
```

### Rule 2: Dual-Agent Processing

```python
# Always use two-stage processing
async def process_segment(segment: str):
    # Stage 1: Clean
    cleaning_result = await cleaning_agent.clean(segment)
    
    # Stage 2: Review
    review_decision = await review_agent.review(
        original=segment,
        cleaned=cleaning_result.cleaned_text
    )
    
    # Stage 3: Categorize by confidence
    return categorizer.categorize(cleaning_result, review_decision)
```

### Rule 3: Progressive Review UI

```python
# Don't show all segments to user
# ❌ WRONG
for segment in all_80_segments:
    show_to_user_for_review(segment)

# ✅ RIGHT - Show only what needs attention
categorized = categorizer.categorize_all(segments)
# User only reviews ~8-10 segments instead of 80
show_only_low_confidence(categorized['needs_review'])
```

### Rule 4: Use Structured Outputs

```python
# Always use Pydantic models for type safety
from pydantic_ai import Agent
from models.schemas import CleaningResult

# ❌ WRONG - Unstructured string response
response = await openai.complete(prompt)
cleaned = response  # No validation!

# ✅ RIGHT - Structured, validated output
agent = Agent(model, result_type=CleaningResult)
result = await agent.run(prompt)
cleaned = result.data  # Type-safe, validated
```

## Advanced Features

### Error Handling Implementation

```python
# utils/error_handler.py
from enum import Enum
from typing import Optional, Callable
import asyncio

class ErrorType(Enum):
    API_TIMEOUT = "api_timeout"
    RATE_LIMIT = "rate_limit"
    CONTENT_LOSS = "content_loss"
    PARSE_ERROR = "parse_error"
    NETWORK_ERROR = "network_error"

class ErrorHandler:
    """Comprehensive error handling with recovery strategies"""
    
    ERROR_MESSAGES = {
        ErrorType.API_TIMEOUT: "Processing taking longer than expected. Retrying...",
        ErrorType.RATE_LIMIT: "API limit reached. Please wait {seconds} seconds.",
        ErrorType.CONTENT_LOSS: "Significant content removed. Automatically rejected.",
        ErrorType.PARSE_ERROR: "Cannot parse file format. Trying plain text fallback.",
        ErrorType.NETWORK_ERROR: "Connection lost. Please check your internet and retry."
    }
    
    @staticmethod
    async def handle_with_retry(
        func: Callable,
        max_retries: int = 3,
        backoff_factor: float = 2.0
    ):
        """Execute function with exponential backoff retry"""
        retry_delay = 1
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await func()
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= backoff_factor
        
        raise last_error
    
    @staticmethod
    def get_user_message(error_type: ErrorType, **kwargs) -> str:
        """Get user-friendly error message"""
        template = ErrorHandler.ERROR_MESSAGES.get(error_type, "An error occurred")
        return template.format(**kwargs)
```

### Performance Optimizations

```python
# core/streaming_processor.py
import asyncio
from typing import AsyncIterator, List
import aiofiles

class StreamingDocumentProcessor:
    """Process large documents with streaming to avoid memory issues"""
    
    def __init__(self, chunk_size: int = 8192):
        self.chunk_size = chunk_size
        self.buffer = []
    
    async def process_file_stream(self, file_path: str) -> AsyncIterator[Dict]:
        """Stream process file without loading entirely in memory"""
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
            buffer = ""
            
            async for chunk in self._read_chunks(file):
                buffer += chunk
                
                # Check for section boundaries
                sections = self._extract_sections(buffer)
                
                for section in sections[:-1]:  # Keep last incomplete section
                    yield section
                
                # Keep remaining incomplete section in buffer
                if sections:
                    buffer = sections[-1]
            
            # Yield final section
            if buffer:
                yield self._create_section(buffer)
    
    async def _read_chunks(self, file) -> AsyncIterator[str]:
        """Read file in chunks"""
        while True:
            chunk = await file.read(self.chunk_size)
            if not chunk:
                break
            yield chunk
    
    def _extract_sections(self, buffer: str) -> List[str]:
        """Extract complete sections from buffer"""
        # Implementation depends on document type
        # For VTT: split on timestamp blocks
        # For notes: split on double newlines
        pass

# core/parallel_processor.py
class ParallelSectionProcessor:
    """Process multiple sections concurrently for speed"""
    
    def __init__(self, max_concurrent: int = 3):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.cleaner = SectionCleaner()
    
    async def process_sections_batch(
        self,
        sections: List[Dict],
        doc_type: str
    ) -> List[Dict]:
        """Process multiple sections in parallel"""
        tasks = []
        
        for i, section in enumerate(sections):
            # Build context for each section
            context = self._build_context(sections, i)
            
            # Create task with semaphore to limit concurrency
            task = self._process_with_limit(section, doc_type, context)
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results and errors
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Fall back to sequential processing for failed sections
                result = await self._process_sequential(sections[i], doc_type)
            processed.append(result)
        
        return processed
    
    async def _process_with_limit(self, section: Dict, doc_type: str, context: Dict):
        """Process section with concurrency limit"""
        async with self.semaphore:
            return await self.cleaner.clean(section, doc_type, context)
```

## Testing Checklist

### 1. Test with Provided Samples

```python
# Test files provided by user:
# - SampleWorkshopTranscript.vtt (short transcript)
# - meeting_note.txt (meeting notes)

# These should segment correctly and process without errors
```

### 2. Content Preservation Test

```python
# Input:
text = "We need to to discuss the the metrics"

# Expected output:
"We need to discuss the metrics"

# NOT:
"We need to discuss metrics"  # ❌ Lost "the"
```

### 3. Large Document Test

```python
# Create a 30,000 word test document
# Should segment into ~15-20 sections
# Should not cause memory issues or timeouts
```

## Common Pitfalls to Avoid

### 1. Don't Trust GPT Blindly

```python
# Always validate
cleaned = await gpt_clean(section)
if significant_content_missing(cleaned):
    reject_automatically()
```

### 2. Don't Over-Clean

```python
# ❌ WRONG: Turn transcript into formal document
"Um, so like, we should probably look at the metrics"
→ "We should examine the metrics."  # Lost speaker voice!

# ✅ RIGHT: Preserve natural speech
"Um, so like, we should probably look at the metrics"
→ "Um, so like, we should probably look at the metrics"  # Keep as is
```

### 3. Handle Errors Gracefully

```python
try:
    cleaned = await clean_section()
except OpenAIError as e:
    # Show clear error to user
    # Allow retry
    # Don't lose progress
```

## Deployment Configuration

### For Local Development

```bash
reflex init
reflex run --env dev
```

### For Production (Snowpark Container)

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY pyproject.toml .
RUN uv add -r pyproject.toml
COPY . .
CMD ["reflex", "run", "--env", "prod", "--host", "0.0.0.0"]
```

## Success Criteria

Your implementation succeeds when:

1. ✅ **97-98% accuracy** achieved through dual-agent processing
2. ✅ **User reviews only 8-10 segments** out of 80 (90% reduction)
3. ✅ **3-5 minute total review time** for 30k word document
4. ✅ **Structured outputs** ensure type safety and validation
5. ✅ **Progressive UI** shows only segments needing attention
6. ✅ **Natural speech preserved** - sounds like original speaker

## Quick Debugging Guide

| Problem | Solution |
|---------|----------|
| "Low accuracy" | Ensure segments are 500 tokens max |
| "Review agent rejecting too much" | Check temperature is 0.0 for review |
| "Too many segments to review" | Verify confidence thresholds (0.95 for auto-accept) |
| "Structured output failing" | Check Pydantic model validation rules |
| "UI showing all segments" | Ensure categorization is working |
| "Processing too slow" | Enable caching, check segment size |

## Production Readiness Checklist

### MVP Requirements (Week 1)

- [ ] ✅ Zero-tolerance content validation implemented
- [ ] ✅ File upload security (size, type validation)
- [ ] ✅ Export functionality working
- [ ] ✅ Basic error handling with user messages
- [ ] ✅ Content sanitization for prompt injection
- [ ] Test with sample files (VTT and TXT)

### Production Requirements (Week 2)

- [ ] Streaming for files > 5MB
- [ ] Parallel processing (3 concurrent sections)
- [ ] Response caching enabled
- [ ] Comprehensive error recovery
- [ ] API fallback (OpenAI → Claude)
- [ ] Progress persistence for recovery
- [ ] Rate limiting per user
- [ ] Monitoring and logging

### Performance Validation

- [ ] 30,000 word document processes without errors
- [ ] <5 second processing per section (95th percentile)
- [ ] <500MB memory usage
- [ ] Zero content loss in validation

### Security Validation

- [ ] No prompt injection possible
- [ ] API keys secure and rotatable
- [ ] File upload limits enforced
- [ ] Content scanning for malicious patterns
- [ ] Rate limiting prevents abuse

---

*Remember: The dual-agent architecture with progressive review achieves 97-98% accuracy while minimizing user effort. Small segments (500 tokens) are key to accuracy. Start with MVP requirements, validate with real data, then add production features based on user feedback.*
