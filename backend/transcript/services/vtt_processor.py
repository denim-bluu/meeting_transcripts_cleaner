import re
import time

import structlog

from backend.transcript.models import VTTChunk, VTTEntry

logger = structlog.get_logger(__name__)


class VTTProcessor:
    """Parse VTT files and create token-based chunks."""

    ## Regex patterns for VTT parsing
    # Parse timestamps such as "00:00:00.000 --> 00:00:01.000"
    TIMESTAMP_PATTERN = (
        r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
    )
    # Parse speaker tags such as <v SpeakerName> or Speaker:
    SPEAKER_PATTERN = r"<v\s+([^>]+)>(.*?)</v>"
    SIMPLE_SPEAKER_PATTERN = r"^([^:]+):\s*(.*)"

    def parse_vtt(self, content: str) -> list[VTTEntry]:
        """
        Parse VTT content into entries.

        Algorithm:
        1. Split by double newline to get cue blocks
        2. For each block: extract cue_id, timestamps, speaker, text
        3. Handle multi-line text within <v> tags
        4. Convert timestamps to seconds
        """
        start_time = time.time()
        logger.info("Starting VTT parsing")

        entries: list[VTTEntry] = []
        # Normalize line endings to handle both Unix (\n) and Windows (\r\n) formats
        normalized_content = content.replace("\r\n", "\n").replace("\r", "\n")
        blocks = normalized_content.strip().split("\n\n")

        skipped_blocks = 0
        invalid_timestamp_blocks = 0
        missing_speaker_blocks = 0

        for block_idx, block in enumerate(blocks):
            # Skip WEBVTT header and empty blocks
            if "WEBVTT" in block or not block.strip():
                skipped_blocks += 1
                continue

            lines = block.strip().split("\n")
            # Skip blocks with less than 2 lines
            if len(lines) < 2:
                skipped_blocks += 1
                continue

            # Determine if first line is cue_id or timestamp
            # Check if first line looks like a timestamp
            timestamp_match = re.search(self.TIMESTAMP_PATTERN, lines[0])
            if timestamp_match:
                # No cue_id, first line is timestamp
                cue_id = f"cue_{block_idx}"
                timestamp_line = lines[0]
                text_lines = lines[1:]
            else:
                # First line is cue_id, second line is timestamp
                if len(lines) < 3:
                    skipped_blocks += 1
                    continue
                cue_id = lines[0]
                timestamp_line = lines[1]
                text_lines = lines[2:]

            # Parse timestamps
            timestamp_match = re.search(self.TIMESTAMP_PATTERN, timestamp_line)
            if not timestamp_match:
                invalid_timestamp_blocks += 1
                logger.warning(
                    "Invalid timestamp format in block",
                    block_index=block_idx,
                    timestamp_line=timestamp_line,
                    cue_id=cue_id,
                )
                continue

            # Convert to seconds
            start_time = (
                int(timestamp_match.group(1)) * 3600
                + int(timestamp_match.group(2)) * 60
                + int(timestamp_match.group(3))
                + int(timestamp_match.group(4)) / 1000
            )

            end_time = (
                int(timestamp_match.group(5)) * 3600
                + int(timestamp_match.group(6)) * 60
                + int(timestamp_match.group(7))
                + int(timestamp_match.group(8)) / 1000
            )

            # Parse speaker and text (may be multi-line)
            # text_lines was already determined above based on cue_id presence
            full_text = " ".join(text_lines)

            speaker = None
            text = None

            # Try <v Speaker> format first
            speaker_match = re.search(self.SPEAKER_PATTERN, full_text)
            if speaker_match:
                speaker = speaker_match.group(1).strip()
                text = speaker_match.group(2).strip()
            else:
                # Try Speaker: format
                simple_match = re.match(self.SIMPLE_SPEAKER_PATTERN, full_text)
                if simple_match:
                    speaker = simple_match.group(1).strip()
                    text = simple_match.group(2).strip()

            if speaker and text:
                entry = VTTEntry(
                    cue_id=cue_id,
                    start_time=start_time,
                    end_time=end_time,
                    speaker=speaker,
                    text=text,
                )
                entries.append(entry)

                logger.debug(
                    "Parsed VTT entry",
                    entry_index=len(entries),
                    cue_id=cue_id,
                    speaker=speaker,
                    duration_seconds=end_time - start_time,
                    text_length=len(text),
                    text_preview=text[:30] + "..." if len(text) > 30 else text,
                )
            else:
                missing_speaker_blocks += 1
                logger.warning(
                    "No speaker found in block",
                    block_index=block_idx,
                    cue_id=cue_id,
                    text_content=full_text[:50],
                )

        processing_time = time.time() - start_time
        speakers = list({entry.speaker for entry in entries})

        logger.info(
            "VTT parsing completed",
            processing_time_ms=int(processing_time * 1000),
            total_entries=len(entries),
            unique_speakers=len(speakers),
        )

        return entries

    def create_chunks(
        self, entries: list[VTTEntry], target_tokens: int = 500
    ) -> list[VTTChunk]:
        """
        Group entries into chunks by token count.

        Algorithm:
        1. Iterate through entries
        2. Add to current chunk until target_tokens reached
        3. Create new chunk when limit exceeded
        4. Never split an entry across chunks

        Token estimation: character_count / 4
        """
        start_time = time.time()
        logger.info(
            "Starting VTT chunking",
            total_entries=len(entries),
            target_tokens=target_tokens,
            estimated_chunks=len(entries) * 25 // target_tokens,  # rough estimate
        )

        chunks: list[VTTChunk] = []
        current_chunk_entries: list[VTTEntry] = []
        current_tokens = 0
        chunk_id = 0

        speaker_switches_in_chunk = 0
        last_speaker = None

        for _, entry in enumerate[VTTEntry](entries):
            entry_tokens = len(entry.text) / 4

            # Track speaker switches for analytics
            if last_speaker != entry.speaker:
                speaker_switches_in_chunk += 1
                last_speaker = entry.speaker

            # When the chunk is full, create a new chunk
            if current_tokens + entry_tokens > target_tokens and current_chunk_entries:
                # Save current chunk
                chunks.append(
                    VTTChunk(
                        chunk_id=chunk_id,
                        entries=current_chunk_entries.copy(),
                        token_count=int(current_tokens),
                    )
                )
                chunk_id += 1
                current_chunk_entries = []
                current_tokens = 0
                speaker_switches_in_chunk = 0

            current_chunk_entries.append(entry)
            current_tokens += entry_tokens

        # Don't forget last chunk
        if current_chunk_entries:
            chunks.append(
                VTTChunk(
                    chunk_id=chunk_id,
                    entries=current_chunk_entries,
                    token_count=int(current_tokens),
                )
            )

        processing_time = time.time() - start_time

        # Calculate analytics
        logger.info(
            "VTT chunking completed",
            processing_time_ms=int(processing_time * 1000),
            total_chunks=len(chunks),
        )

        return chunks
