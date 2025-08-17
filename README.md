# Meeting Intelligence System

## About The Project

### The Challenge

Modern organizations generate thousands of hours of meeting recordings, but extracting actionable intelligence from transcripts remains a manual, time-intensive process. Existing solutions either lack technical depth, hallucinate information, or fail to preserve critical business context.

### Our Solution

The **Meeting Intelligence System** is a production-ready, microservices-based platform that transforms raw VTT transcripts into executive-quality summaries while preserving technical accuracy and business context. Built with modern cloud-native patterns and advanced AI agents.

---

## System Architecture

### Architectural Principles

Our system follows **simplified microservices** and **clean architecture** principles optimized for containerized deployments:

- **Stateless Services**: Horizontally scalable services with no persistent state
- **Event-Driven Architecture**: Asynchronous processing with background task queues
- **In-Memory Caching**: Simple TTL-based task storage for ephemeral container environments
- **Dependency Injection**: Loose coupling through interface-based design
- **Pure Function Agents**: Stateless AI agents for concurrent safety and reliability

### High-Level Architecture

```mermaid
graph TB
    subgraph "External Layer"
        UI[Client Applications]
        LB[Load Balancer]
    end

    subgraph "API Gateway Layer"
        GW[API Gateway<br/>Rate Limiting & Auth]
    end

    subgraph "Application Services Layer"
        subgraph "Frontend Service :8501"
            SF[Streamlit Web UI]
            AC[API Client<br/>Type-Safe HTTP]
            SM[State Management]
        end

        subgraph "Backend Service :8000"
            FA[FastAPI Application<br/>Async REST API]
            BT[Background Task Queue<br/>Celery-style Processing]
            HC[Health Check Service]
        end
    end

    subgraph "Domain Layer - AI Agent Orchestra"
        subgraph "Pure Pydantic AI Agents"
            CA[Cleaning Agent<br/>Grammar & Context]
            RA[Review Agent<br/>Quality Validation]
            EA[Extraction Agent<br/>Dynamic Instructions]
            DSA[Direct Synthesis Agent]
            HSA[Hierarchical Synthesis Agent]
            SSA[Segment Synthesis Agent]
        end

        subgraph "Orchestration Services"
            IO[Intelligence Orchestrator<br/>Concurrent Processing]
            TS[Transcript Service<br/>Pipeline Management]
        end
    end

    subgraph "Infrastructure Layer"
        subgraph "Task Management"
            TC[Task Cache<br/>In-Memory TTL Storage]
            FS[File System<br/>Transcript Storage]
        end

        subgraph "External APIs"
            OAI[OpenAI API<br/>o3/o3-mini Models]
            LC[LangChain<br/>Semantic Processing]
        end

        subgraph "Observability"
            LOG[Structured Logging<br/>structlog]
            MET[Metrics Collection]
            TRC[Distributed Tracing]
        end
    end

    %% User flow
    UI --> LB
    LB --> GW
    GW --> SF
    SF --> AC
    AC -->|HTTP/JSON| FA

    %% Backend processing flow
    FA --> BT
    BT --> TS
    TS --> IO

    %% Agent orchestration
    IO --> CA
    IO --> RA
    IO --> EA
    IO --> DSA
    IO --> HSA
    IO --> SSA

    %% Data flow
    CA --> OAI
    RA --> OAI
    EA --> OAI
    DSA --> OAI
    HSA --> OAI
    SSA --> OAI

    EA --> LC
    TS --> TC
    TS --> FS

    %% Health and monitoring
    FA --> HC
    HC --> LOG
    IO --> MET
    BT --> TRC

    %% Styling
    classDef frontend fill:#e1f5fe,stroke:#01579b,color:#000
    classDef backend fill:#e8f5e9,stroke:#2e7d32,color:#000
    classDef agents fill:#fff3e0,stroke:#ef6c00,color:#000
    classDef data fill:#f3e5f5,stroke:#7b1fa2,color:#000
    classDef external fill:#ffebee,stroke:#c62828,color:#000

    class SF,AC,SM frontend
    class FA,BT,HC,IO,TS backend
    class CA,RA,EA,DSA,HSA,SSA agents
    class TC,FS data
    class OAI,LC external
```

### Service Boundaries & Responsibilities

#### Frontend Service (`frontend/`)

**Responsibility**: User interface and user experience management

- **Streamlit Web Application**: Interactive UI with real-time progress tracking
- **API Client**: Type-safe HTTP client with automatic retry and error handling
- **State Management**: Session state persistence and form validation
- **Responsive Design**: Mobile-friendly interface with modern UX patterns

#### Backend Service (`backend/`)

**Responsibility**: Business logic orchestration and API management

- **FastAPI Application**: High-performance async REST API with OpenAPI documentation
- **Background Task Processing**: Queue-based long-running operations with progress tracking
- **Health Check System**: Kubernetes-ready liveness and readiness probes
- **Request/Response Pipeline**: Validation, serialization, and error handling

#### Agent Domain (`backend/agents/`)

**Responsibility**: AI-powered content processing and intelligence extraction

- **Pure Pydantic AI Agents**: Stateless, concurrent-safe agents with built-in validation
- **Dynamic Instruction System**: Context-aware prompt adaptation based on processing requirements
- **Quality Assurance Pipeline**: Multi-stage validation with automatic retry mechanisms
- **Concurrent Processing**: Parallel execution with proper error isolation

### Data Flow Architecture

```mermaid
sequenceDiagram
    participant UI as Frontend UI
    participant API as Backend API
    participant BG as Background Tasks
    participant AG as Agent Orchestra
    participant AI as OpenAI API
    participant TC as Task Cache

    UI->>API: POST /api/v1/transcript/process
    API->>BG: Queue transcript cleaning task
    API-->>UI: 202 Accepted + task_id

    BG->>AG: Initialize cleaning agent
    AG->>AI: Clean transcript chunks
    AI-->>AG: Cleaned content
    AG->>TC: Store intermediate results
    BG-->>API: Task progress update

    UI->>API: GET /api/v1/task/{task_id}
    API-->>UI: Task status + results

    UI->>API: POST /api/v1/intelligence/extract
    API->>BG: Queue intelligence extraction

    BG->>AG: Orchestrate extraction pipeline

    par Concurrent Processing
        AG->>AI: Extract insights (chunk 1)
        AG->>AI: Extract insights (chunk 2)
        AG->>AI: Extract insights (chunk N)
    end

    AG->>AI: Synthesize intelligence
    AI-->>AG: Final intelligence report
    AG->>TC: Store intelligence results
    BG-->>API: Extraction complete

    API-->>UI: Intelligence summary + actions
```

---

## Getting Started

### Docker Deployment

```bash
# Build containers
just docker-build

# Start all services
just docker-run

# View logs
just docker-logs

# Stop services
just docker-stop
```

### Access Points

Once deployed, access the system at:

- 🖥️ **Frontend Application**: http://localhost:8501
- 🔧 **Backend API**: http://localhost:8000
- 📚 **API Documentation**: http://localhost:8000/docs
- ❤️ **Health Check**: http://localhost:8000/health

<p align="right">(<a href="#top">back to top</a>)</p>

---

## Usage

### Quick Start Example

1. **Upload VTT Transcript**
    - Navigate to http://localhost:8501
    - Upload your meeting transcript (.vtt file)
    - Wait for cleaning and review completion

2. **Extract Intelligence**
    - Go to Intelligence tab
    - Select detail level (Standard/Comprehensive/Technical Focus)
    - Click "Extract Intelligence"
    - Review generated summary and action items

### API Reference

#### Core Endpoints

**Upload & Process Transcript**

```http
POST /api/v1/transcript/process
Content-Type: multipart/form-data

Form Data:
- file: transcript.vtt
- detail_level: "comprehensive" (optional)
```

**Extract Meeting Intelligence**

```http
POST /api/v1/intelligence/extract
Content-Type: application/json

{
  "transcript_id": "uuid-task-id",
  "detail_level": "comprehensive"
}
```

**Task Management**

```http
GET /api/v1/task/{task_id}
DELETE /api/v1/task/{task_id}
```

**System Health**

```http
GET /health        # Basic health check
GET /health/ready  # Readiness probe
GET /docs         # OpenAPI documentation
```

#### Response Examples

**Intelligence Extraction Response:**

```json
{
    "transcript_id": "abc-123",
    "intelligence": {
        "summary": "# Executive Summary\n\nComprehensive meeting analysis...",
        "action_items": [
            {
                "description": "Complete database migration testing",
                "owner": "Engineering Team",
                "due_date": "Next Tuesday"
            }
        ],
        "processing_stats": {
            "chunks_processed": 12,
            "insights_extracted": 48,
            "processing_time_seconds": 6.2
        }
    }
}
```
