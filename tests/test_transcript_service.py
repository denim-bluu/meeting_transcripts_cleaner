"""
Simple, focused tests for TranscriptService.

Tests only essential functionality for the simplified 2-layer architecture.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from models.vtt import VTTChunk, VTTEntry
from services.transcript_service import TranscriptService


class TestTranscriptServiceSimple:
    """Essential tests for TranscriptService."""

    def test_service_initialization(self):
        """Test service initializes correctly."""
        service = TranscriptService("test-key")
        assert service.processor is not None
        assert service.cleaner is not None
        assert service.reviewer is not None
        assert service.semaphore._value == 10  # Default concurrency

    def test_process_vtt_basic(self):
        """Test basic VTT processing."""
        service = TranscriptService("test-key")

        vtt_content = """WEBVTT

1
00:00:01.000 --> 00:00:05.000
<v Speaker1>Hello world.</v>

2
00:00:05.000 --> 00:00:10.000
<v Speaker2>How are you?</v>"""

        result = service.process_vtt(vtt_content)

        assert "entries" in result
        assert "chunks" in result
        assert "speakers" in result
        assert "duration" in result

        assert len(result["entries"]) == 2
        assert len(result["chunks"]) > 0
        assert len(result["speakers"]) == 2
        assert result["duration"] == 10.0

    def test_process_vtt_empty(self):
        """Test processing empty VTT."""
        service = TranscriptService("test-key")

        result = service.process_vtt("WEBVTT")

        assert len(result["entries"]) == 0
        assert len(result["chunks"]) == 0
        assert len(result["speakers"]) == 0
        assert result["duration"] == 0

    @pytest.mark.asyncio
    async def test_clean_transcript_basic(self):
        """Test basic transcript cleaning."""
        service = TranscriptService("test-key")

        # Mock the AI agents to return Pydantic models
        with (
            patch.object(
                service.cleaner, "clean_chunk", new_callable=AsyncMock
            ) as mock_clean,
            patch.object(
                service.reviewer, "review_chunk", new_callable=AsyncMock
            ) as mock_review,
        ):
            from models.agents import CleaningResult, ReviewResult

            mock_clean.return_value = CleaningResult(
                cleaned_text="Cleaned text", confidence=0.9, changes_made=[]
            )
            mock_review.return_value = ReviewResult(
                quality_score=0.8, issues=[], accept=True
            )

            # Create simple transcript
            transcript = {
                "entries": [VTTEntry("1", 0.0, 5.0, "Speaker", "Test")],
                "chunks": [
                    VTTChunk(0, [VTTEntry("1", 0.0, 5.0, "Speaker", "Test")], 10)
                ],
                "speakers": ["Speaker"],
                "duration": 5.0,
            }

            result = await service.clean_transcript(transcript)

            assert "cleaned_chunks" in result
            assert "review_results" in result
            assert "final_transcript" in result
            assert "processing_stats" in result

            assert len(result["cleaned_chunks"]) == 1
            assert len(result["review_results"]) == 1
            assert "Cleaned text" in result["final_transcript"]

    @pytest.mark.asyncio
    async def test_clean_transcript_with_progress(self):
        """Test cleaning with progress callback."""
        service = TranscriptService("test-key")
        progress_calls = []

        def progress_callback(progress: float, message: str):
            progress_calls.append((progress, message))

        with (
            patch.object(
                service.cleaner, "clean_chunk", new_callable=AsyncMock
            ) as mock_clean,
            patch.object(
                service.reviewer, "review_chunk", new_callable=AsyncMock
            ) as mock_review,
        ):
            mock_clean.return_value = {
                "cleaned_text": "Cleaned text",
                "confidence": 0.9,
                "changes_made": [],
            }
            mock_review.return_value = {
                "quality_score": 0.8,
                "issues": [],
                "accept": True,
            }

            transcript = {
                "entries": [VTTEntry("1", 0.0, 5.0, "Speaker", "Test")],
                "chunks": [
                    VTTChunk(0, [VTTEntry("1", 0.0, 5.0, "Speaker", "Test")], 10)
                ],
                "speakers": ["Speaker"],
                "duration": 5.0,
            }

            await service.clean_transcript(transcript, progress_callback)

            # Should have received progress calls
            assert len(progress_calls) > 0
            final_progress, final_message = progress_calls[-1]
            assert final_progress == 1.0
            assert "Finalizing" in final_message

    def test_export_txt_format(self):
        """Test TXT export format."""
        service = TranscriptService("test-key")

        transcript = {
            "entries": [VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            "chunks": [
                VTTChunk(0, [VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")], 10)
            ],
            "speakers": ["Speaker"],
            "duration": 5.0,
            "final_transcript": "Speaker: Hello world",
        }

        result = service.export(transcript, "txt")
        assert result == "Speaker: Hello world"

    def test_export_vtt_format(self):
        """Test VTT export format."""
        service = TranscriptService("test-key")

        transcript = {
            "entries": [VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            "chunks": [],
            "speakers": ["Speaker"],
            "duration": 5.0,
        }

        result = service.export(transcript, "vtt")

        assert result.startswith("WEBVTT")
        assert "00:00:00.000 --> 00:00:05.000" in result
        assert "<v Speaker>Hello world</v>" in result

    def test_export_json_format(self):
        """Test JSON export format."""
        service = TranscriptService("test-key")

        transcript = {
            "entries": [VTTEntry("1", 0.0, 5.0, "Speaker", "Hello world")],
            "chunks": [],
            "speakers": ["Speaker"],
            "duration": 5.0,
        }

        result = service.export(transcript, "json")

        # Should be valid JSON
        parsed = json.loads(result)
        assert "entries" in parsed
        assert "speakers" in parsed
        assert "duration" in parsed

    def test_export_unsupported_format(self):
        """Test error handling for unsupported format."""
        service = TranscriptService("test-key")

        transcript = {"entries": [], "chunks": [], "speakers": [], "duration": 0}

        with pytest.raises(ValueError, match="Unsupported format"):
            service.export(transcript, "unsupported")

    def test_timestamp_formatting(self):
        """Test VTT timestamp formatting."""
        service = TranscriptService("test-key")

        assert service._format_timestamp(0.0) == "00:00:00.000"
        assert service._format_timestamp(65.123) == "00:01:05.123"
        assert service._format_timestamp(3661.456) == "01:01:01.456"


class TestTranscriptServiceIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """Test complete VTT -> clean -> export workflow."""
        service = TranscriptService("test-key")

        vtt_content = """WEBVTT

1
00:00:01.000 --> 00:00:05.000
<v Speaker>Um, hello world.</v>"""

        with (
            patch.object(
                service.cleaner, "clean_chunk", new_callable=AsyncMock
            ) as mock_clean,
            patch.object(
                service.reviewer, "review_chunk", new_callable=AsyncMock
            ) as mock_review,
        ):
            mock_clean.return_value = {
                "cleaned_text": "Speaker: Hello world.",
                "confidence": 0.95,
                "changes_made": ["Removed filler words"],
            }
            mock_review.return_value = {
                "quality_score": 0.9,
                "issues": [],
                "accept": True,
            }

            # 1. Process VTT
            transcript = service.process_vtt(vtt_content)
            assert len(transcript["entries"]) == 1

            # 2. Clean transcript
            cleaned = await service.clean_transcript(transcript)
            assert "final_transcript" in cleaned

            # 3. Export in different formats
            txt_export = service.export(cleaned, "txt")
            vtt_export = service.export(cleaned, "vtt")
            json_export = service.export(cleaned, "json")

            assert len(txt_export) > 0
            assert vtt_export.startswith("WEBVTT")
            assert json.loads(json_export)  # Should be valid JSON
