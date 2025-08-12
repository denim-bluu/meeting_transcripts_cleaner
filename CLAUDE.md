# Simplified VTT Processing Implementation Plan

## Task Tracker
| Task | Owner | Status |
|------|-------|--------|
| Delete all over-engineered VTT files | Sonnet | ✅ Done |
| Create simple VTT parser | Sonnet | ✅ Done |
| Create token-based chunker | Sonnet | ✅ Done |
| Create AI cleaning agent | Sonnet | ✅ Done |
| Create AI review agent | Sonnet | ✅ Done |
| Create unified transcript service | Sonnet | ✅ Done |
| Update UI for simplified flow | Sonnet | ✅ Done |
| Remove complex configurations | Sonnet | ✅ Done |
| Test with quarterly_review_meeting.vtt | Sonnet | ✅ Done |
| Fix API key configuration | Sonnet | ✅ Done |
| Validate all acceptance criteria | Sonnet | ✅ Done |

## Implementation Plan

### 1. High-Level Overview
Replace the over-engineered 4-layer architecture with a simple 2-layer approach: Parse VTT directly into entries, then chunk by token count. No ConversationTurns, no ProcessingSegments, no EnrichedContext. Process chunks with AI agents using simple previous/next text for context. Target: <1000 lines total code, <2 sec per chunk processing.

### 2. Detailed Steps

- [ ] **Delete all existing VTT modules** - Remove core/context_builder.py, core/conversation_chunker.py, core/vtt_parser.py, core/vtt_cleaning_agent.py, core/vtt_review_agent.py, models/vtt_models.py, models/vtt_document.py, services/vtt_transcript_service.py
- [ ] **Create models/vtt.py** - Simple dataclasses for VTTEntry and VTTChunk
- [ ] **Create core/vtt_processor.py** - Parser using regex, chunker using token counting
- [ ] **Create core/ai_agents.py** - TranscriptCleaner and TranscriptReviewer with structured prompts
- [ ] **Create services/transcript_service.py** - Orchestration with progress tracking
- [ ] **Update pages/1_📤_Upload_Process.py** - Use new TranscriptService
- [ ] **Remove complex configs** - Delete overlap, context_window, preserve_sentences settings
- [ ] **Test end-to-end** - Validate with quarterly_review_meeting.vtt

### 3. Code Stubs / Public Interfaces

```python
# models/vtt.py
from dataclasses import dataclass
from typing import List

@dataclass
class VTTEntry:
    """Single VTT cue exactly as it appears in the file."""
    cue_id: str          # e.g., "d700e97e-1c7f-4753-9597-54e5e43b4642/18-0"
    start_time: float    # seconds from 00:00:00.000
    end_time: float      # seconds from 00:00:00.000
    speaker: str         # e.g., "Rian Campbell"
    text: str           # e.g., "OK. Yeah."

@dataclass
class VTTChunk:
    """Group of VTT entries chunked by token count for AI processing."""
    chunk_id: int        # Sequential: 0, 1, 2...
    entries: List[VTTEntry]
    token_count: int     # Approximate tokens (len(text) / 4)
    
    def to_transcript_text(self) -> str:
        """Format entries as 'Speaker: text' for AI processing."""
        lines = []
        for entry in self.entries:
            lines.append(f"{entry.speaker}: {entry.text}")
        return "\n".join(lines)

# core/vtt_processor.py
import re
from typing import List
from models.vtt import VTTEntry, VTTChunk

class VTTProcessor:
    """Parse VTT files and create token-based chunks."""
    
    # Regex patterns for VTT parsing
    TIMESTAMP_PATTERN = r'(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})\.(\d{3})'
    SPEAKER_PATTERN = r'<v\s+([^>]+)>(.*?)</v>'
    
    def parse_vtt(self, content: str) -> List[VTTEntry]:
        """
        Parse VTT content into entries.
        
        Algorithm:
        1. Split by double newline to get cue blocks
        2. For each block: extract cue_id, timestamps, speaker, text
        3. Handle multi-line text within <v> tags
        4. Convert timestamps to seconds
        """
        entries = []
        blocks = content.strip().split('\n\n')
        
        for block in blocks:
            if 'WEBVTT' in block or not block.strip():
                continue
                
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
                
            # Line 0: cue_id
            # Line 1: timestamps
            # Line 2+: speaker and text
            
            # Parse and return entries
        return entries
    
    def create_chunks(self, entries: List[VTTEntry], target_tokens: int = 500) -> List[VTTChunk]:
        """
        Group entries into chunks by token count.
        
        Algorithm:
        1. Iterate through entries
        2. Add to current chunk until target_tokens reached
        3. Create new chunk when limit exceeded
        4. Never split an entry across chunks
        
        Token estimation: character_count / 4
        """
        chunks = []
        current_chunk_entries = []
        current_tokens = 0
        chunk_id = 0
        
        for entry in entries:
            entry_tokens = len(entry.text) / 4
            
            if current_tokens + entry_tokens > target_tokens and current_chunk_entries:
                # Save current chunk
                chunks.append(VTTChunk(
                    chunk_id=chunk_id,
                    entries=current_chunk_entries.copy(),
                    token_count=int(current_tokens)
                ))
                chunk_id += 1
                current_chunk_entries = []
                current_tokens = 0
            
            current_chunk_entries.append(entry)
            current_tokens += entry_tokens
        
        # Don't forget last chunk
        if current_chunk_entries:
            chunks.append(VTTChunk(
                chunk_id=chunk_id,
                entries=current_chunk_entries,
                token_count=int(current_tokens)
            ))
        
        return chunks

# core/ai_agents.py
import asyncio
from typing import Dict, Optional
from openai import AsyncOpenAI
from models.vtt import VTTChunk

class TranscriptCleaner:
    """Clean transcript chunks using OpenAI API."""
    
    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
    
    async def clean_chunk(self, chunk: VTTChunk, prev_text: str = "") -> Dict:
        """
        Clean a single chunk with minimal context.
        
        Returns:
        {
            "cleaned_text": str,  # Cleaned version maintaining speakers
            "confidence": float,  # 0.0 to 1.0
            "changes_made": List[str]  # What was fixed
        }
        
        Prompt template:
        - Role: You are a transcript editor
        - Task: Clean up speech-to-text errors
        - Rules: Preserve speaker labels, fix grammar, remove filler words
        - Context: Previous chunk ending (last 100 chars)
        - Input: Current chunk text
        - Output: JSON with cleaned_text, confidence, changes_made
        """
        context = prev_text[-200:] if prev_text else ""
        
        prompt = f"""Clean this meeting transcript chunk. Preserve all speaker names exactly.

Previous context: ...{context}

Current chunk:
{chunk.to_transcript_text()}

Fix grammar, remove filler words (um, uh), but keep the conversational tone.
Return JSON with: cleaned_text, confidence (0-1), changes_made (list)."""

        # Call OpenAI and parse response
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": "You are a transcript editor."},
                     {"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        # Parse and return JSON response

class TranscriptReviewer:
    """Review cleaned transcripts for quality."""
    
    def __init__(self, api_key: str, model: str = "gpt-4"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
    
    async def review_chunk(self, original: VTTChunk, cleaned: str) -> Dict:
        """
        Review cleaned text quality.
        
        Returns:
        {
            "quality_score": float,  # 0.0 to 1.0
            "issues": List[str],     # Problems found
            "accept": bool           # Whether to accept cleaning
        }
        
        Prompt focuses on:
        - Speaker preservation
        - Meaning preservation
        - Grammar correctness
        - Natural flow
        """
        prompt = f"""Review this transcript cleaning quality.

Original:
{original.to_transcript_text()}

Cleaned:
{cleaned}

Check: speaker names preserved, meaning intact, grammar fixed, flows naturally.
Return JSON with: quality_score (0-1), issues (list), accept (boolean)."""

        # Call OpenAI and parse response

# services/transcript_service.py
from typing import Dict, List, Optional, Callable
from models.vtt import VTTEntry, VTTChunk
from core.vtt_processor import VTTProcessor
from core.ai_agents import TranscriptCleaner, TranscriptReviewer

class TranscriptService:
    """Orchestrate the complete VTT processing pipeline."""
    
    def __init__(self, api_key: str):
        self.processor = VTTProcessor()
        self.cleaner = TranscriptCleaner(api_key)
        self.reviewer = TranscriptReviewer(api_key)
        
    def process_vtt(self, content: str) -> Dict:
        """
        Parse and chunk VTT file.
        
        Returns:
        {
            "entries": List[VTTEntry],  # All 1308 entries
            "chunks": List[VTTChunk],   # ~40 chunks
            "speakers": List[str],      # Unique speakers
            "duration": float           # Total seconds
        }
        """
        entries = self.processor.parse_vtt(content)
        chunks = self.processor.create_chunks(entries)
        
        speakers = list(set(e.speaker for e in entries))
        duration = max(e.end_time for e in entries) if entries else 0
        
        return {
            "entries": entries,
            "chunks": chunks,
            "speakers": sorted(speakers),
            "duration": duration
        }
    
    async def clean_transcript(
        self, 
        transcript: Dict,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Dict:
        """
        Run AI cleaning and review on all chunks.
        
        Args:
            transcript: Output from process_vtt()
            progress_callback: Called with (progress_pct, status_msg)
        
        Returns transcript with added:
        {
            ...existing fields...,
            "cleaned_chunks": List[Dict],  # Cleaning results per chunk
            "review_results": List[Dict],  # Review results per chunk
            "final_transcript": str        # Complete cleaned text
        }
        """
        chunks = transcript["chunks"]
        cleaned_chunks = []
        review_results = []
        
        for i, chunk in enumerate(chunks):
            if progress_callback:
                progress_callback(i / len(chunks), f"Cleaning chunk {i+1}/{len(chunks)}")
            
            # Get previous chunk text for context
            prev_text = cleaned_chunks[-1]["cleaned_text"] if cleaned_chunks else ""
            
            # Clean chunk
            clean_result = await self.cleaner.clean_chunk(chunk, prev_text)
            cleaned_chunks.append(clean_result)
            
            # Review cleaning
            review_result = await self.reviewer.review_chunk(chunk, clean_result["cleaned_text"])
            review_results.append(review_result)
        
        # Combine all cleaned text
        final_transcript = "\n\n".join(c["cleaned_text"] for c in cleaned_chunks)
        
        transcript["cleaned_chunks"] = cleaned_chunks
        transcript["review_results"] = review_results
        transcript["final_transcript"] = final_transcript
        
        return transcript
    
    def export(self, transcript: Dict, format: str) -> str:
        """
        Export cleaned transcript in requested format.
        
        Formats:
        - "vtt": WEBVTT with cleaned text, preserving timestamps
        - "txt": Simple text with "Speaker: text" format
        - "json": Complete data structure
        
        For VTT: Reconstruct using original timestamps but cleaned text
        For TXT: Simple concatenation of cleaned chunks
        For JSON: Return full transcript dict as JSON string
        """
        if format == "vtt":
            # Reconstruct VTT with cleaned text
            lines = ["WEBVTT", ""]
            # Map cleaned text back to entries and format
            
        elif format == "txt":
            return transcript.get("final_transcript", "")
            
        elif format == "json":
            import json
            return json.dumps(transcript, indent=2, default=str)

# pages/1_📤_Upload_Process.py updates needed:
"""
1. Import new TranscriptService instead of old VTTTranscriptService
2. Replace complex document processing with simple:
   - service = TranscriptService(api_key)
   - transcript = service.process_vtt(content)
   - await service.clean_transcript(transcript, progress_callback)
3. Update progress display to show chunk-based progress
4. Simplify metrics display (just chunks, speakers, duration)
5. Add export buttons calling service.export(transcript, format)
"""
```

### 4. Cleanup Actions

**Delete these files entirely:**
- `core/context_builder.py`
- `core/conversation_chunker.py` 
- `core/vtt_parser.py`
- `core/vtt_cleaning_agent.py`
- `core/vtt_review_agent.py`
- `models/vtt_models.py`
- `models/vtt_document.py`
- `services/vtt_transcript_service.py`
- `test_vtt_pipeline.py`
- `test_ai_processing.py`

**Remove from config files:**
- In `config.py`: Remove token_overlap, preserve_sentence_boundaries, context_window_size
- In `utils/config_manager.py`: Remove all overlap calculation logic
- In `pages/3_⚙️_Settings.py`: Remove UI controls for above settings

### 5. Critical Implementation Details

**VTT Parsing Algorithm:**
```python
def parse_vtt(self, content: str) -> List[VTTEntry]:
    entries = []
    blocks = content.strip().split('\n\n')
    
    for block in blocks:
        if 'WEBVTT' in block or not block.strip():
            continue
        
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
            
        cue_id = lines[0]
        
        # Parse timestamps
        timestamp_match = re.search(self.TIMESTAMP_PATTERN, lines[1])
        if not timestamp_match:
            continue
        
        # Convert to seconds
        start_time = int(timestamp_match.group(1)) * 3600 + \
                    int(timestamp_match.group(2)) * 60 + \
                    int(timestamp_match.group(3)) + \
                    int(timestamp_match.group(4)) / 1000
        
        end_time = int(timestamp_match.group(5)) * 3600 + \
                  int(timestamp_match.group(6)) * 60 + \
                  int(timestamp_match.group(7)) + \
                  int(timestamp_match.group(8)) / 1000
        
        # Parse speaker and text (may be multi-line)
        text_lines = lines[2:]
        full_text = ' '.join(text_lines)
        
        speaker_match = re.search(self.SPEAKER_PATTERN, full_text)
        if speaker_match:
            speaker = speaker_match.group(1).strip()
            text = speaker_match.group(2).strip()
            
            entries.append(VTTEntry(
                cue_id=cue_id,
                start_time=start_time,
                end_time=end_time,
                speaker=speaker,
                text=text
            ))
    
    return entries
```

**Token Counting:**
- Use simple approximation: 1 token ≈ 4 characters
- `token_count = len(text) / 4`

**Progress Tracking:**
- Call progress_callback with (percentage, message)
- Percentage: current_chunk / total_chunks
- Message: "Cleaning chunk X of Y"

**Error Handling:**
- Wrap all API calls in try/except
- On error, store error in result dict and continue
- Never fail entire pipeline for one chunk

### 6. Acceptance Criteria

1. **Parse correctly**: 1,308 entries from quarterly_review_meeting.vtt, "Nathaniel Meixler" in 955 entries
2. **Simple chunks**: 35-45 chunks of ~500 tokens each
3. **Fast processing**: <2 seconds per chunk (with API calls)
4. **Small codebase**: <1000 lines total across all new files
5. **No abstraction layers**: Only VTTEntry → VTTChunk
6. **AI integration**: Both cleaning and review return valid JSON
7. **Progress tracking**: UI shows real-time progress
8. **Export works**: All three formats (VTT, TXT, JSON) produce valid output
9. **No old references**: Zero imports of deleted modules
10. **Error resilient**: One chunk failure doesn't stop pipeline