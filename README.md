# Meeting Transcripts Cleaner

## AI-Powered VTT Processing with Concurrent Architecture

A streamlined transcript cleaning system that processes VTT (WebVTT) files through a concurrent dual-agent AI architecture. Built for enterprise-grade reliability with structured error handling and real-time progress reporting.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [System Design](#system-design)
- [Core Features](#core-features)
- [Technology Stack](#technology-stack)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [API Reference](#api-reference)

## Architecture Overview

### Concurrent Processing Pipeline

```mermaid
graph TB
    A[VTT File] --> B[VTTProcessor<br/>Regex Parser]
    B --> C[VTTEntry<br/>cue_id, timestamps, speaker, text]
    C --> D[VTTChunk<br/>500-token groups]
    
    D --> E[TranscriptService<br/>Concurrent Orchestration]
    E --> F[Batch Processing<br/>10 chunks per batch]
    
    F --> G[TranscriptCleaner<br/>AI Agent - o3-mini]
    F --> H[TranscriptReviewer<br/>AI Agent - o3-mini]
    
    G --> I[CleaningResult<br/>confidence + changes]
    H --> J[ReviewResult<br/>quality + acceptance]
    
    I --> K[Export Pipeline]
    J --> K
    K --> L[VTT/TXT/JSON Output]

    style A fill:#e3f2fd
    style D fill:#fff9c4
    style G fill:#f3e5f5
    style H fill:#f3e5f5
    style K fill:#e8f5e9
```

### System Responsibilities

**VTTProcessor**: Regex-based parsing of VTT cue blocks into structured entries, token-based chunking
**TranscriptService**: Concurrent orchestration with rate limiting, progress tracking, error resilience  
**AI Agents**: Structured cleaning and quality review with confidence scoring
**UI Layer**: Real-time progress reporting with batch metrics and throughput analysis

## Core Features

### 🚀 Concurrent Processing Architecture

- **Batch Processing**: 10-chunk batches with configurable concurrency (default: 10 for o3-mini stability)
- **Rate Limiting**: Configurable throttling (default: 50 requests/minute) with exponential backoff
- **Progress Reporting**: Real-time batch metrics with throughput analysis and ETA calculations
- **Error Resilience**: Individual chunk failures isolated with structured error handling

### 🎯 VTT-Native Processing

- **Direct Parsing**: Regex-based VTT cue block extraction with multi-line text support
- **Speaker Preservation**: Exact `<v Speaker>` label maintenance throughout pipeline
- **Timestamp Accuracy**: Original VTT timestamps preserved for export compatibility
- **Token-Based Chunking**: 500-token chunks with character-based estimation (length ÷ 4)

### 🤖 Dual-Agent AI System

- **TranscriptCleaner**: Grammar correction, filler removal, conversation flow optimization
- **TranscriptReviewer**: Quality validation with confidence scoring and acceptance thresholds
- **Structured Output**: JSON responses with change tracking and quality metrics
- **Context Preservation**: Previous 200 characters for conversation continuity

## System Design

### Component Architecture

```mermaid
graph TB
    subgraph "Data Models"
        VE[VTTEntry<br/>cue_id, start_time, end_time<br/>speaker, text]
        VC[VTTChunk<br/>chunk_id, entries list<br/>token_count]
        CR[CleaningResult<br/>cleaned_text, confidence<br/>changes_made list]
        RR[ReviewResult<br/>quality_score, accept<br/>issues_found list]
    end

    subgraph "Core Processing"
        VP[VTTProcessor<br/>• parse_vtt<br/>• create_chunks]
        TC[TranscriptCleaner<br/>• clean_chunk<br/>• AI agent wrapper]
        TR[TranscriptReviewer<br/>• review_chunk<br/>• Quality validation]
    end

    subgraph "Service Orchestration"
        TS[TranscriptService<br/>• Concurrent batch processing<br/>• Rate limiting & throttling<br/>• Progress callback system<br/>• Error handling & retries]
    end

    subgraph "UI Layer"
        UP[Upload & Process<br/>• Real-time progress display<br/>• 4-column metrics<br/>• Batch/throughput tracking]
        RP[Review & Export<br/>• Results validation<br/>• Multi-format export]
    end

    VE --> VC
    VC --> VP
    VP --> TS
    TC --> TS
    TR --> TS
    CR --> TS
    RR --> TS
    TS --> UP
    TS --> RP
```

### Processing Flow

```mermaid
sequenceDiagram
    participant UI as Streamlit UI
    participant TS as TranscriptService
    participant VP as VTTProcessor
    participant TC as TranscriptCleaner
    participant TR as TranscriptReviewer

    UI->>TS: process_vtt(content)
    TS->>VP: parse_vtt()
    VP->>TS: VTTEntry[]
    TS->>VP: create_chunks()
    VP->>TS: VTTChunk[]

    TS->>TS: Initialize batch processing
    
    loop For each batch (10 chunks)
        TS->>UI: progress_callback(batch_info)
        
        par Concurrent processing
            TS->>TC: clean_chunk()
            TC->>TS: CleaningResult
            TS->>TR: review_chunk()
            TR->>TS: ReviewResult
        end
    end
    
    TS->>UI: Final results + export options
```

## Technology Stack

| Component           | Technology                 | Responsibility                           |
| ------------------- | -------------------------- | ---------------------------------------- |
| **Framework**       | Streamlit                  | UI components and real-time progress    |
| **AI Processing**   | OpenAI AsyncAPI            | Concurrent API calls with rate limiting  |
| **Models**          | o3-mini (default)          | Text cleaning and quality review         |
| **Concurrency**     | asyncio + Semaphore        | Batch processing with controlled limits  |
| **Rate Limiting**   | asyncio-throttle           | Request throttling and backoff           |
| **Logging**         | structlog                  | Structured, contextual logging           |
| **Package Manager** | uv                         | Fast dependency management               |

## Installation

### Setup

1. **Clone repository**

```bash
git clone https://github.com/denim-bluu/meeting_transcripts_cleaner.git
cd meeting_transcripts_cleaner
```

1. **Install dependencies**

```bash
uv sync
```

1. **Configure environment**

```bash
# Create .env file
cat > .env << EOF
OPENAI_API_KEY=sk-your-api-key-here
CLEANING_MODEL=o3-mini
REVIEW_MODEL=o3-mini
EOF
```

1. **Run application**

```bash
streamlit run streamlit_app.py
```

## Usage

### System Operation

1. **Upload VTT File**: Streamlit interface accepts WebVTT format files
2. **Automatic Processing**:
   - VTTProcessor parses entries and creates 500-token chunks
   - TranscriptService orchestrates concurrent batch processing
   - Progress callbacks provide real-time feedback with batch metrics
3. **AI Processing**: Dual-agent system (Cleaner → Reviewer) processes each chunk
4. **Export Options**: Results available in VTT, TXT, or JSON formats

### API Usage

```python
from services.transcript_service import TranscriptService

# Initialize with concurrent processing
service = TranscriptService(
    api_key="your-openai-key",
    max_concurrent=10,  # For o3-mini stability
    rate_limit=50       # Requests per minute
)

# Process VTT content
with open("meeting.vtt", "r") as f:
    content = f.read()

# Parse and chunk
transcript = service.process_vtt(content)
print(f"Created {len(transcript['chunks'])} chunks")

# Clean with progress tracking
def progress_callback(pct, status):
    print(f"{pct:.1f}% - {status}")

import asyncio
cleaned = asyncio.run(
    service.clean_transcript(transcript, progress_callback)
)

# Results contain CleaningResult and ReviewResult for each chunk
for chunk in cleaned['results']:
    print(f"Confidence: {chunk['cleaning'].confidence}")
    print(f"Quality: {chunk['review'].quality_score}")
```

## Configuration

### Service Parameters

```python
# TranscriptService configuration
TranscriptService(
    api_key="sk-...",
    max_concurrent=10,    # Concurrent requests (10 optimal for o3-mini)
    rate_limit=50         # Requests per minute (adjust for API tier)
)
```

### Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-xxx

# Optional model selection  
CLEANING_MODEL=o3-mini    # Text cleaning model
REVIEW_MODEL=o3-mini      # Quality review model
```

## API Reference

### TranscriptService

**`process_vtt(content: str) -> dict`**

- Parses VTT content into entries and chunks
- Returns structured data with entries, chunks, speakers, duration

**`clean_transcript(transcript: dict, progress_callback=None) -> dict`**

- Processes chunks through AI agents concurrently
- Returns results with CleaningResult and ReviewResult for each chunk
- Progress callback receives (percentage, status_message)

### Data Models

**VTTEntry**: `cue_id`, `start_time`, `end_time`, `speaker`, `text`  
**VTTChunk**: `chunk_id`, `entries (list)`, `token_count`  
**CleaningResult**: `cleaned_text`, `confidence`, `changes_made (list)`  
**ReviewResult**: `quality_score`, `accept`, `issues_found (list)`
