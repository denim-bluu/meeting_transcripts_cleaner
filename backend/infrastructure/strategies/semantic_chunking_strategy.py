"""Semantic chunking strategy wrapper."""

from models.transcript import VTTChunk
from utils.semantic_chunker import SemanticChunker


class SemanticChunkingStrategy:
    """Wrapper for SemanticChunker implementing ChunkingStrategy protocol."""

    def __init__(self):
        self._chunker = SemanticChunker()

    def create_chunks(self, vtt_chunks: list[VTTChunk]) -> list[str]:
        return self._chunker.create_chunks(vtt_chunks)
