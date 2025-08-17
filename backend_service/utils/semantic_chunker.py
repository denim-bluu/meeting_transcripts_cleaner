from langchain.text_splitter import RecursiveCharacterTextSplitter
import structlog

from backend_service.models.transcript import VTTChunk

logger = structlog.get_logger(__name__)


class SemanticChunker:
    """
    Semantic chunking using LangChain for meeting transcripts.

    Responsibilities:
    - Convert VTTChunks to single transcript text
    - Split into 1500-token semantic chunks with overlap (optimized for comprehensive extraction)
    - Respect speaker boundaries and sentence structure
    - Return chunks suitable for LLM processing

    Expected behavior:
    - 60-min meeting: 35 VTTChunks -> 15-25 semantic chunks (increased granularity)
    - Preserves speaker context across boundaries
    - No mid-sentence splits
    - More extraction opportunities with smaller, focused chunks
    """

    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 200):
        # Convert token-based parameters to character-based for RecursiveCharacterTextSplitter
        # Assumption: 1 token ≈ 4 characters (standard GPT tokenizer approximation)
        char_chunk_size = chunk_size * 4
        char_overlap = chunk_overlap * 4

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=char_chunk_size,
            chunk_overlap=char_overlap,
            separators=["\n\n", "\n", ". ", " "],
            length_function=len,
        )
        logger.info(
            "SemanticChunker initialized",
            token_chunk_size=chunk_size,
            token_overlap=chunk_overlap,
            char_chunk_size=char_chunk_size,
            char_overlap=char_overlap,
        )

    def create_chunks(self, vtt_chunks: list[VTTChunk]) -> list[str]:
        """Convert VTT chunks to semantic chunks."""
        # Combine all VTT chunks into single transcript
        full_transcript = "\n".join(chunk.to_transcript_text() for chunk in vtt_chunks)

        # Split semantically
        semantic_chunks = self.splitter.split_text(full_transcript)

        logger.info(
            "Semantic chunking completed",
            vtt_chunks=len(vtt_chunks),
            semantic_chunks=len(semantic_chunks),
            avg_chunk_size=sum(len(c) for c in semantic_chunks) // len(semantic_chunks),
        )

        return semantic_chunks
