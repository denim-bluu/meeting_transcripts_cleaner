"""
Document processor for parsing and segmenting meeting transcripts.

This module handles the initial processing of uploaded documents, including:
- Content extraction and validation
- Token counting and segmentation (500 tokens per segment)
- Sentence boundary preservation
- Overlap management between segments
"""

from datetime import UTC, datetime
import re
from uuid import uuid4

import structlog
import tiktoken

from config import get_processing_config
from models.schemas import (
    DocumentSegment,
    ProcessingStatus,
    ProcessingStatusEnum,
    TranscriptDocument,
)
from utils.config_manager import get_merged_processing_config

logger = structlog.get_logger(__name__)


class DocumentProcessor:
    """Processes documents by parsing and segmenting them for the dual-agent system."""

    _vtt_mode: bool = False  # Controls overlap behavior for VTT files

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        """
        Initialize the document processor.

        Args:
            encoding_name: Name of the tiktoken encoding to use for token counting
        """
        # Use merged config that includes session overrides
        try:
            processing_config = get_merged_processing_config()
        except Exception:
            # Fallback to base config if overrides fail
            processing_config = get_processing_config()

        self.encoding = tiktoken.get_encoding(encoding_name)
        self.max_tokens = processing_config.max_section_tokens
        self.overlap_tokens = processing_config.token_overlap
        self.min_tokens = processing_config.min_segment_tokens
        self.preserve_sentences = processing_config.preserve_sentence_boundaries

        # Sentence boundary regex pattern
        self.sentence_pattern = re.compile(
            r"(?<=[.!?])\s+(?=[A-Z])",  # Basic sentence boundaries
            re.MULTILINE,
        )

        # Paragraph boundary pattern
        self.paragraph_pattern = re.compile(r"\n\s*\n", re.MULTILINE)

    def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in the given text.

        Args:
            text: Input text to count tokens for

        Returns:
            Number of tokens in the text
        """
        return len(self.encoding.encode(text))

    def split_into_sentences(self, text: str) -> list[str]:
        """
        Split text into sentences while preserving structure.

        Args:
            text: Input text to split

        Returns:
            List of sentences
        """
        # First split by paragraphs to preserve structure
        paragraphs = self.paragraph_pattern.split(text)
        sentences = []

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            # Split paragraph into sentences
            para_sentences = self.sentence_pattern.split(paragraph)

            # Add sentences, preserving paragraph breaks
            for _i, sentence in enumerate(para_sentences):
                sentence = sentence.strip()
                if sentence:
                    sentences.append(sentence)

            # Add paragraph break marker (except for last paragraph)
            if paragraph != paragraphs[-1]:
                sentences.append("\n\n")

        return sentences

    def create_segments_with_sentences(self, text: str) -> list[DocumentSegment]:
        """
        Create segments by respecting sentence boundaries.

        Args:
            text: Input text to segment

        Returns:
            List of document segments
        """
        sentences = self.split_into_sentences(text)
        segments = []
        current_segment = ""
        current_start = 0
        sequence_number = 1

        for sentence in sentences:
            # Check if adding this sentence would exceed token limit
            test_segment = current_segment + (" " if current_segment else "") + sentence
            test_tokens = self.count_tokens(test_segment)

            if test_tokens <= self.max_tokens or not current_segment:
                # Add sentence to current segment
                current_segment = test_segment
            else:
                # Finalize current segment if it meets minimum token requirement
                if self.count_tokens(current_segment) >= self.min_tokens:
                    segment = self._create_segment(
                        content=current_segment,
                        start_index=current_start,
                        sequence_number=sequence_number,
                        original_text=text,
                    )
                    segments.append(segment)
                    sequence_number += 1

                # Start new segment with overlap
                if self.overlap_tokens > 0 and segments and not getattr(self, '_vtt_mode', False):
                    overlap_text = self._get_overlap_text(
                        current_segment, self.overlap_tokens
                    )
                    current_segment = (
                        overlap_text + (" " if overlap_text else "") + sentence
                    )
                    # Adjust start index to account for overlap
                    current_start = segments[-1].end_index - len(overlap_text)
                else:
                    current_segment = sentence
                    current_start = segments[-1].end_index if segments else 0

        # Add final segment if it has content
        if current_segment and self.count_tokens(current_segment) >= self.min_tokens:
            segment = self._create_segment(
                content=current_segment,
                start_index=current_start,
                sequence_number=sequence_number,
                original_text=text,
            )
            segments.append(segment)

        return segments

    def _create_segment(
        self, content: str, start_index: int, sequence_number: int, original_text: str
    ) -> DocumentSegment:
        """
        Create a DocumentSegment instance with proper indices.

        Args:
            content: Segment content
            start_index: Starting character index
            sequence_number: Sequence number of the segment
            original_text: Original full text for index calculation

        Returns:
            DocumentSegment instance
        """
        # Calculate end index by finding content in original text
        # This is approximate since we may have overlap/modifications
        end_index = start_index + len(content)

        # Ensure end index doesn't exceed text length
        if end_index > len(original_text):
            end_index = len(original_text)

        return DocumentSegment(
            content=content.strip(),
            token_count=self.count_tokens(content),
            start_index=start_index,
            end_index=end_index,
            sequence_number=sequence_number,
        )

    def _get_overlap_text(self, text: str, overlap_tokens: int) -> str:
        """
        Get the last N tokens worth of text for overlap.

        Args:
            text: Source text to get overlap from
            overlap_tokens: Number of tokens to include in overlap

        Returns:
            Overlap text
        """
        if overlap_tokens <= 0:
            return ""

        # Split into words and work backwards
        words = text.split()
        if not words:
            return ""

        # Build overlap from end of text
        overlap_text = ""
        for i in range(len(words) - 1, -1, -1):
            test_overlap = " ".join(words[i:])
            if self.count_tokens(test_overlap) <= overlap_tokens:
                overlap_text = test_overlap
            else:
                break

        return overlap_text

    def parse_vtt_content(self, vtt_content: str) -> str:
        """
        Parse VTT (WebVTT) content and extract speaker text.

        Args:
            vtt_content: Raw VTT content

        Returns:
            Parsed text with speaker identification
        """
        # Split content into blocks separated by double newlines
        blocks = vtt_content.strip().split("\n\n")
        parsed_segments = []

        for block in blocks:
            block = block.strip()

            # Skip empty blocks and VTT header
            if not block or block == "WEBVTT":
                continue

            lines = block.split("\n")
            speaker_content = None
            plain_content = []

            # Look for speaker content in this block
            for line in lines:
                line = line.strip()

                # Skip timestamp lines (contain -->)
                if "-->" in line:
                    continue

                # Check for speaker tags like <v John D.>content</v>
                speaker_match = re.match(r"<v\s+([^>]+)>(.*)</v>$", line)
                if speaker_match:
                    speaker_name = speaker_match.group(1).strip()
                    speaker_text = speaker_match.group(2).strip()
                    if speaker_text:
                        speaker_content = f"{speaker_name}: {speaker_text}"
                    break

                # Handle multi-line speaker content (opening tag on one line)
                opening_match = re.match(r"<v\s+([^>]+)>(.*)$", line)
                if opening_match:
                    speaker_name = opening_match.group(1).strip()
                    speaker_text = opening_match.group(2).strip()

                    # Look for closing tag in remaining lines of this block
                    remaining_lines = lines[lines.index(line) + 1:]
                    full_content = [speaker_text] if speaker_text else []

                    for next_line in remaining_lines:
                        next_line = next_line.strip()
                        if next_line.endswith("</v>"):
                            # Remove closing tag and add content
                            content = next_line[:-4].strip()
                            if content:
                                full_content.append(content)
                            break
                        elif next_line:
                            full_content.append(next_line)

                    if full_content:
                        speaker_content = f"{speaker_name}: {' '.join(full_content)}"
                    break

                # Handle plain content without speaker tags
                elif line and not line.startswith("NOTE"):
                    plain_content.append(line)

            # Add the processed content - prefer speaker content, fallback to plain
            if speaker_content:
                parsed_segments.append(speaker_content)
            elif plain_content:
                parsed_segments.append(" ".join(plain_content))

        return "\n\n".join(parsed_segments)

    def process_document(
        self, filename: str, content: str, file_size: int, content_type: str
    ) -> TranscriptDocument:
        """
        Process a complete document by parsing and segmenting it.

        Args:
            filename: Name of the original file
            content: Document content text
            file_size: Size of the file in bytes
            content_type: MIME type of the file

        Returns:
            TranscriptDocument with segments ready for processing

        Raises:
            ValueError: If document content is invalid or too short
        """
        logger.info(
            "Processing document",
            # Key identifier (flat)
            phase="document_processing",
            # Document info (grouped)
            document={"filename": filename, "file_size_bytes": file_size}
        )

        # Validate content
        if not content or not content.strip():
            raise ValueError("Document content is empty")

        content = content.strip()
        total_tokens = self.count_tokens(content)

        if total_tokens < self.min_tokens:
            raise ValueError(
                f"Document is too short ({total_tokens} tokens). "
                f"Minimum required: {self.min_tokens} tokens"
            )

        logger.info(
            "Document tokenized",
            # Key identifier (flat)
            phase="tokenization",
            # Processing results (grouped)
            processing={"total_tokens": total_tokens}
        )

        # Create segments using sentence-based segmentation
        segments = self.create_segments_with_sentences(content)
        logger.info("Created segments preserving sentence boundaries", phase="segmentation")

        logger.info(
            "Segments created",
            # Key identifier (flat)
            phase="segmentation",
            # Processing results (grouped)
            processing={"segment_count": len(segments)}
        )

        # Log segment statistics
        if segments:
            token_counts = [seg.token_count for seg in segments]
            logger.info(
                "Segment token statistics",
                # Key identifier (flat)
                phase="segmentation",
                # Statistics (grouped)
                stats={"min_tokens": min(token_counts), "max_tokens": max(token_counts), "avg_tokens": sum(token_counts)/len(token_counts)}
            )

        # Create document with required processing_status
        processing_status = ProcessingStatus(
            document_id=str(uuid4()),
            status=ProcessingStatusEnum.PENDING,
            total_segments=len(segments),
            processed_segments=0,
            failed_segments=0,
            auto_accept_count=0,
            quick_review_count=0,
            detailed_review_count=0,
            ai_flagged_count=0,
            started_at=datetime.now(UTC),
            completed_at=None,
            estimated_completion=None,
        )

        document = TranscriptDocument(
            filename=filename,
            original_content=content,
            file_size_bytes=file_size,
            content_type=content_type,
            segments=segments,
            max_tokens_per_segment=self.max_tokens,
            processing_status=processing_status,
            cleaning_model="o3-mini",
            review_model="o3-mini",
        )

        logger.info("Document processing completed successfully", phase="document_processing")
        return document
