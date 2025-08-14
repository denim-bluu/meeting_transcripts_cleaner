from langchain.text_splitter import RecursiveCharacterTextSplitter
from models.vtt import VTTChunk
import structlog

logger = structlog.get_logger(__name__)

class SemanticChunker:
    """
    Semantic chunking using LangChain for meeting transcripts.
    
    Responsibilities:
    - Convert VTTChunks to single transcript text
    - Split into 3000-token semantic chunks with overlap
    - Respect speaker boundaries and sentence structure
    - Return chunks suitable for LLM processing
    
    Expected behavior:
    - 60-min meeting: 35 VTTChunks -> 8-12 semantic chunks
    - Preserves speaker context across boundaries
    - No mid-sentence splits
    """
    
    def __init__(self, chunk_size: int = 3000, chunk_overlap: int = 200):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " "],
            length_function=len,
        )
        logger.info("SemanticChunker initialized", chunk_size=chunk_size, overlap=chunk_overlap)
    
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
            avg_chunk_size=sum(len(c) for c in semantic_chunks) // len(semantic_chunks)
        )
        
        return semantic_chunks