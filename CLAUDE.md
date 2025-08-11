# VTT-Native Transcript Processing Implementation Plan

## Task Tracker
| Task | Owner | Status |
|------|-------|--------|
| Create VTT data models | Sonnet | Pending |
| Implement VTT parser | Sonnet | Pending |
| Build conversation chunker | Sonnet | Pending |
| Create context builder | Sonnet | Pending |
| Update cleaning agent | Sonnet | Pending |
| Update review agent | Sonnet | Pending |
| Refactor transcript service | Sonnet | Pending |
| Update Streamlit UI | Sonnet | Pending |
| Remove obsolete code | Sonnet | Pending |
| Test with real VTT files | Sonnet | Pending |

## Implementation Plan

### 1. High-Level Overview
Replace the current dual-mode text/VTT processing system with a VTT-native architecture that preserves speaker attribution and temporal metadata throughout the pipeline. The system will chunk transcripts by natural speaker turns instead of arbitrary token counts, provide 2000+ token context windows to AI agents instead of 100 characters, and achieve 10x performance improvement by eliminating conversational chaos that confuses AI models.

### 2. Detailed Steps

#### Phase 1: Data Models & Parser
- [ ] Create `models/vtt_models.py` with VTTEntry, ConversationTurn, ProcessingSegment, EnrichedContext dataclasses
- [ ] Create `core/vtt_parser.py` to parse VTT format into List[VTTEntry] preserving cue_id, timestamps, speaker, text
- [ ] Test parser with `examples/files/quarterly_review_meeting.vtt` (1,308 entries, 348 speaker turns expected)

#### Phase 2: Conversation Chunking
- [ ] Create `core/conversation_chunker.py` to group VTT entries by speaker turns (consecutive same-speaker entries)
- [ ] Implement merge_to_segments() to combine turns into ~500 token ProcessingSegments
- [ ] Validate creates 35-40 segments from quarterly_review_meeting.vtt (not 52 as current system)

#### Phase 3: Context Builder
- [ ] Create `core/context_builder.py` to assemble EnrichedContext with 2-3 previous/next segments
- [ ] Include speaker history, temporal position (0.0-1.0), all speakers list
- [ ] Ensure minimum 2000 tokens context (vs current 100 chars)

#### Phase 4: Agent Updates
- [ ] Update `core/cleaning_agent.py` clean_segment() signature: `async def clean_segment(self, context: EnrichedContext) -> CleaningResult`
- [ ] Replace cleaning prompt to include: current_speaker, meeting_progress, num_speakers, previous_speakers
- [ ] Update `core/review_agent.py` review_segment() signature: `async def review_segment(self, context: EnrichedContext, cleaning_result: CleaningResult) -> ReviewResult`
- [ ] Add speaker consistency validation to review criteria (check speaker names preserved, transitions natural)
- [ ] Both agents must log context.current_segment.turns to verify speaker awareness

#### Phase 5: Service Integration
- [ ] `services/transcript_service.py` Line 63-64: DELETE parse_vtt_content() call and _vtt_mode flag
- [ ] Line 68: Add `vtt_entries = self.vtt_parser.parse(content)`
- [ ] Line 69: Add `turns = self.conversation_chunker.chunk_by_speaker_turns(vtt_entries)`
- [ ] Line 70: Add `segments = self.conversation_chunker.merge_to_segments(turns, 500)`
- [ ] Line 195-200: Replace context dict with `context = self.context_builder.build_context(index, document.processing_segments)`
- [ ] Line 196: Change agent call to `await self.cleaning_agent.clean_segment(context)`
- [ ] Update parallel processing to pass ProcessingSegment not DocumentSegment
- [ ] Store results by segment.id for proper reassembly

#### Phase 6: UI Updates
- [ ] `pages/1_📤_Upload_Process.py` Line 43: Change to show `{len(turns)} speaker turns → {len(segments)} segments`
- [ ] Line 165: Update progress to show `Processing turn {current_turn}/{total_turns}`
- [ ] Line 210-220: Display with `st.markdown(f"**{turn.speaker}** ({turn.start_time:.1f}s): {text}")`
- [ ] `streamlit_app.py`: Add speaker metrics (total speakers, total turns, duration)
- [ ] Create `components/speaker_display.py` with display_speaker_timeline() and display_speaker_stats()
- [ ] Add export buttons for VTT, text with speakers, JSON formats

#### Phase 7: Cleanup
- [ ] Remove all DocumentProcessor text processing methods
- [ ] Delete overlap management code
- [ ] Remove _vtt_mode flag and special cases
- [ ] Delete DocumentSegment model (replaced by ProcessingSegment)

### 3. Code Stubs / Public Interfaces

```python
# models/vtt_models.py
@dataclass
class VTTEntry:
    """Atomic unit of VTT transcript - represents single speaker utterance with timing."""
    cue_id: str
    start_time: float  # seconds
    end_time: float
    speaker: str
    text: str

@dataclass
class ConversationTurn:
    """Natural conversation boundary - consecutive entries from same speaker."""
    speaker: str
    entries: List[VTTEntry]
    start_time: float
    end_time: float
    
@dataclass
class ProcessingSegment:
    """Unit of work for AI agents - contains multiple turns up to token limit."""
    id: str
    turns: List[ConversationTurn]
    token_count: int
    sequence_number: int
    
@dataclass
class EnrichedContext:
    """Full conversation context provided to AI agents for processing."""
    current_segment: ProcessingSegment
    previous_segments: List[ProcessingSegment]  # 2-3
    next_segments: List[ProcessingSegment]      # 2-3
    all_speakers: List[str]
    meeting_progress: float  # 0.0 to 1.0

# core/vtt_parser.py
class VTTParser:
    def parse(self, content: str) -> List[VTTEntry]:
        """Parse raw VTT content into structured entries preserving all metadata."""

# core/conversation_chunker.py
class ConversationChunker:
    def chunk_by_speaker_turns(self, entries: List[VTTEntry]) -> List[ConversationTurn]:
        """Group consecutive same-speaker entries into natural conversation turns."""
    
    def merge_to_segments(self, turns: List[ConversationTurn], target_tokens: int = 500) -> List[ProcessingSegment]:
        """Merge turns into processing segments respecting token limits."""

# core/context_builder.py
class ContextBuilder:
    def build_context(self, segment_index: int, all_segments: List[ProcessingSegment]) -> EnrichedContext:
        """Assemble rich context with adjacent segments and conversation metadata."""

# core/cleaning_agent.py
class CleaningAgent:
    async def clean_segment(self, context: EnrichedContext) -> CleaningResult:
        """Clean transcript segment with full conversation awareness."""

# core/review_agent.py
class ReviewAgent:
    async def review_segment(self, context: EnrichedContext, cleaning_result: CleaningResult) -> ReviewResult:
        """Review cleaned segment with conversation flow understanding."""
```

### 4. Configuration & Session Changes

**Configuration Updates (config.py)**:
```python
# REMOVE these settings
- max_section_tokens = 500  # Replaced by target_tokens in chunker
- token_overlap = 50  # No more overlaps
- preserve_sentence_boundaries = True  # Natural turns handle this

# ADD these settings
+ target_segment_tokens = 500  # Target size for ProcessingSegments
+ min_context_tokens = 2000  # Minimum context for agents
+ max_turns_per_segment = 10  # Prevent too many speaker switches
```

**Session State Schema (streamlit_app.py)**:
```python
# Initialize session state with new structure
if "vtt_document" not in st.session_state:
    st.session_state.vtt_document = None
    st.session_state.vtt_entries = []
    st.session_state.conversation_turns = []
    st.session_state.processing_segments = []
    st.session_state.speakers = []
    st.session_state.cleaning_results = {}
    st.session_state.review_results = {}
```

### 5. Cleanup Actions

**Files to modify/remove methods from:**
- `core/document_processor.py`: DELETE parse_vtt_content(), create_segments_with_sentences(), split_into_sentences(), _get_overlap_text(), _create_segment()
- `services/transcript_service.py`: DELETE lines 63-64 (parse_vtt_content call and _vtt_mode flag)
- `models/schemas.py`: DELETE DocumentSegment class after migrating to ProcessingSegment

**Flags/modes to remove:**
- `_vtt_mode` flag throughout codebase
- `overlap_tokens` configuration and logic
- `preserve_sentences` configuration (natural turns replace this)

**Test files to update:**
- Update all tests expecting DocumentSegment to use ProcessingSegment
- Remove tests for overlap functionality
- Add tests for speaker turn preservation

### 5. Critical Testing Points

**VTT Parser Validation**:
```python
# Test with quarterly_review_meeting.vtt
assert len(vtt_entries) == 1308
assert sum(1 for e in vtt_entries if e.speaker == "Meixler, Nathaniel") == 955
assert all(e.start_time < e.end_time for e in vtt_entries)
```

**Chunking Validation**:
```python
# Natural boundaries test
turns = chunker.chunk_by_speaker_turns(vtt_entries)
assert 340 <= len(turns) <= 360  # Expected ~348
segments = chunker.merge_to_segments(turns, 500)
assert 35 <= len(segments) <= 40  # Not 52 like current system
```

**Context Size Validation**:
```python
# In clean_segment(), add logging
logger.info(f"Context tokens: {len(tokenizer.encode(str(context)))}")
assert len(tokenizer.encode(str(context))) >= 2000  # Must be 2000+ tokens
```

**Export Functionality**:
```python
# utils/export.py - Must support three formats
def export_as_vtt(document: VTTDocument) -> str:
    """WEBVTT\n\n{cue_id}\n{start} --> {end}\n<v {speaker}>{cleaned_text}</v>"""
    
def export_with_speakers(document: VTTDocument) -> str:
    """Speaker: text\n\nSpeaker2: text"""
    
def export_as_json(document: VTTDocument) -> dict:
    """{"speakers": [...], "turns": [...], "segments": [...]}"""
```

### 6. Acceptance Criteria

1. **Parser correctness**: quarterly_review_meeting.vtt parses to exactly 1,308 VTT entries with speaker "Meixler, Nathaniel" appearing 955 times
2. **Natural chunking**: Same file produces 35-40 ProcessingSegments (not 52) with average 3-5 speaker switches per segment (not 27)
3. **Context size**: Every AI agent call receives minimum 2000 tokens of context (verified via logging)
4. **Performance**: 95% of segments process in <5 seconds (current: 30s average, 74s max)
5. **No empty responses**: Zero "Received empty model response" errors in logs
6. **Speaker preservation**: Final output maintains all speaker labels and can be exported as valid VTT
7. **UI displays**: Speaker list, turn counts, and progress by conversation turns visible in Streamlit
8. **Code reduction**: Net removal of 200+ lines of overlap/mode management code
9. **Test coverage**: All existing tests pass with new models, no dangling references to removed code
10. **Real file validation**: Successfully processes VTT exports from Teams, Zoom, and included example files