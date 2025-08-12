"""
Simple, focused tests for VTT processor.

Tests only essential functionality for the simplified 2-layer architecture.
"""

import pytest
from core.vtt_processor import VTTProcessor
from models.vtt import VTTEntry, VTTChunk


class TestVTTProcessorSimple:
    """Essential tests for VTT processor."""
    
    def test_processor_initialization(self):
        """Test processor initializes correctly."""
        processor = VTTProcessor()
        assert hasattr(processor, 'TIMESTAMP_PATTERN')
        assert hasattr(processor, 'SPEAKER_PATTERN')
    
    def test_parse_simple_vtt(self):
        """Test parsing basic VTT content."""
        processor = VTTProcessor()
        vtt_content = """WEBVTT

1
00:00:01.000 --> 00:00:05.000
<v Speaker1>Hello world.</v>

2
00:00:05.000 --> 00:00:10.000
<v Speaker2>How are you?</v>"""
        
        entries = processor.parse_vtt(vtt_content)
        
        assert len(entries) == 2
        assert entries[0].cue_id == "1"
        assert entries[0].speaker == "Speaker1"
        assert entries[0].text == "Hello world."
        assert entries[0].start_time == 1.0
        assert entries[0].end_time == 5.0
    
    def test_parse_handles_empty_content(self):
        """Test parser handles empty content gracefully."""
        processor = VTTProcessor()
        
        entries = processor.parse_vtt("WEBVTT")
        assert len(entries) == 0
        
        entries = processor.parse_vtt("")
        assert len(entries) == 0
    
    def test_parse_handles_malformed_content(self):
        """Test parser handles malformed content gracefully."""
        processor = VTTProcessor()
        
        # Content without proper speaker tags
        malformed = """WEBVTT

1
00:00:01.000 --> 00:00:05.000
Text without speaker tag"""
        
        entries = processor.parse_vtt(malformed)
        assert len(entries) == 0  # Should skip malformed entries
    
    def test_create_chunks_basic(self):
        """Test basic chunk creation."""
        processor = VTTProcessor()
        
        entries = [
            VTTEntry("1", 0.0, 5.0, "Speaker", "Short text."),
            VTTEntry("2", 5.0, 10.0, "Speaker", "Another short piece."),
            VTTEntry("3", 10.0, 15.0, "Speaker", "Final entry."),
        ]
        
        chunks = processor.create_chunks(entries, target_tokens=100)
        
        assert len(chunks) > 0
        assert all(isinstance(chunk, VTTChunk) for chunk in chunks)
        assert all(chunk.chunk_id == i for i, chunk in enumerate(chunks))
        
        # Verify all entries are included
        total_entries = sum(len(chunk.entries) for chunk in chunks)
        assert total_entries == len(entries)
    
    def test_create_chunks_empty_entries(self):
        """Test chunking with empty entries."""
        processor = VTTProcessor()
        chunks = processor.create_chunks([], target_tokens=500)
        assert len(chunks) == 0
    
    def test_create_chunks_large_entry(self):
        """Test that single large entry creates one chunk."""
        processor = VTTProcessor()
        
        large_text = "This is a very long entry " * 50  # Large entry
        entries = [VTTEntry("1", 0.0, 60.0, "Speaker", large_text)]
        
        chunks = processor.create_chunks(entries, target_tokens=50)
        
        # Should still create one chunk even if it exceeds target
        assert len(chunks) == 1
        assert chunks[0].token_count > 50
    
    def test_token_counting_estimation(self):
        """Test token counting estimation is reasonable."""
        processor = VTTProcessor()
        
        # Known text with predictable length
        text = "Hello world test"  # 16 characters
        entries = [VTTEntry("1", 0.0, 5.0, "Speaker", text)]
        
        chunks = processor.create_chunks(entries, target_tokens=100)
        
        assert len(chunks) == 1
        # Token count should be approximately 16 / 4 = 4
        assert 3 <= chunks[0].token_count <= 5
    
    def test_chunk_ordering_preserved(self):
        """Test that chunk ordering preserves entry sequence."""
        processor = VTTProcessor()
        
        entries = [
            VTTEntry("1", 0.0, 5.0, "Speaker1", "First entry."),
            VTTEntry("2", 5.0, 10.0, "Speaker2", "Second entry."),
            VTTEntry("3", 10.0, 15.0, "Speaker3", "Third entry."),
        ]
        
        chunks = processor.create_chunks(entries, target_tokens=20)
        
        # Collect all entries from chunks
        all_entries = []
        for chunk in chunks:
            all_entries.extend(chunk.entries)
        
        # Should be in same order
        assert len(all_entries) == len(entries)
        for i, entry in enumerate(all_entries):
            assert entry.cue_id == entries[i].cue_id


class TestVTTProcessorIntegration:
    """Integration tests for VTT processing."""
    
    def test_full_parse_and_chunk_pipeline(self):
        """Test complete parse -> chunk pipeline."""
        processor = VTTProcessor()
        
        vtt_content = """WEBVTT

d700e97e-1c7f-4753-9597-54e5e43b4642/1-0
00:00:01.000 --> 00:00:05.000
<v John Smith>Um, so welcome everyone to, uh, the quarterly meeting.</v>

d700e97e-1c7f-4753-9597-54e5e43b4642/2-0
00:00:00:05.000 --> 00:00:10.000
<v John Smith>I know we're all, you know, really excited to get started on this.</v>"""
        
        # Parse
        entries = processor.parse_vtt(vtt_content)
        assert len(entries) == 2
        
        # Chunk
        chunks = processor.create_chunks(entries, target_tokens=200)
        assert len(chunks) >= 1
        
        # Verify pipeline integrity
        all_chunk_entries = []
        for chunk in chunks:
            all_chunk_entries.extend(chunk.entries)
        
        assert len(all_chunk_entries) == len(entries)
        
        # Test transcript text generation
        for chunk in chunks:
            text = chunk.to_transcript_text()
            assert len(text) > 0
            assert ":" in text  # Should have speaker: format