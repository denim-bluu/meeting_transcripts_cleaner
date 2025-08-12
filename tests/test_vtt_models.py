"""
Unit tests for VTT data models.

Tests the VTTEntry and VTTChunk dataclasses for:
- Basic instantiation and attribute access
- Data integrity and validation
- to_transcript_text() method functionality
- Edge cases and error conditions
"""

import pytest

from models.vtt import VTTChunk, VTTEntry


class TestVTTEntry:
    """Test cases for VTTEntry dataclass."""
    
    def test_vtt_entry_creation(self):
        """Test basic VTTEntry creation with valid data."""
        entry = VTTEntry(
            cue_id="test-1",
            start_time=1.5,
            end_time=5.2,
            speaker="John Doe",
            text="Hello world"
        )
        
        assert entry.cue_id == "test-1"
        assert entry.start_time == 1.5
        assert entry.end_time == 5.2
        assert entry.speaker == "John Doe"
        assert entry.text == "Hello world"
    
    def test_vtt_entry_with_complex_data(self):
        """Test VTTEntry with complex real-world data."""
        entry = VTTEntry(
            cue_id="d700e97e-1c7f-4753-9597-54e5e43b4642/18-0",
            start_time=123.456,
            end_time=128.789,
            speaker="Meixler, Nathaniel",
            text="Um, so we need to, uh, discuss the quarterly results."
        )
        
        assert entry.cue_id == "d700e97e-1c7f-4753-9597-54e5e43b4642/18-0"
        assert entry.start_time == 123.456
        assert entry.end_time == 128.789
        assert entry.speaker == "Meixler, Nathaniel"
        assert entry.text == "Um, so we need to, uh, discuss the quarterly results."
    
    def test_vtt_entry_with_empty_text(self):
        """Test VTTEntry with empty text."""
        entry = VTTEntry(
            cue_id="empty-1",
            start_time=0.0,
            end_time=1.0,
            speaker="Speaker",
            text=""
        )
        
        assert entry.text == ""
        assert entry.cue_id == "empty-1"
    
    def test_vtt_entry_with_special_characters(self):
        """Test VTTEntry with special characters in text and speaker name."""
        entry = VTTEntry(
            cue_id="special-1",
            start_time=10.0,
            end_time=15.0,
            speaker="José María",
            text="¡Hola! How are you? 😊"
        )
        
        assert entry.speaker == "José María"
        assert entry.text == "¡Hola! How are you? 😊"
    
    def test_vtt_entry_zero_duration(self):
        """Test VTTEntry with zero duration."""
        entry = VTTEntry(
            cue_id="zero-duration",
            start_time=5.0,
            end_time=5.0,
            speaker="Speaker",
            text="Quick response"
        )
        
        assert entry.start_time == entry.end_time
        assert entry.text == "Quick response"
    
    def test_vtt_entry_long_text(self):
        """Test VTTEntry with very long text."""
        long_text = "This is a very long piece of text " * 50
        entry = VTTEntry(
            cue_id="long-text",
            start_time=0.0,
            end_time=60.0,
            speaker="Verbose Speaker",
            text=long_text
        )
        
        assert len(entry.text) > 1000
        assert entry.text == long_text


class TestVTTChunk:
    """Test cases for VTTChunk dataclass."""
    
    def test_vtt_chunk_creation(self, sample_vtt_entries):
        """Test basic VTTChunk creation."""
        chunk = VTTChunk(
            chunk_id=0,
            entries=sample_vtt_entries,
            token_count=150
        )
        
        assert chunk.chunk_id == 0
        assert len(chunk.entries) == 3
        assert chunk.token_count == 150
    
    def test_vtt_chunk_to_transcript_text(self, sample_vtt_entries):
        """Test to_transcript_text() method."""
        chunk = VTTChunk(
            chunk_id=0,
            entries=sample_vtt_entries,
            token_count=150
        )
        
        expected_text = (
            "John Smith: Welcome everyone to the quarterly meeting.\n"
            "John Smith: I know we're all excited to get started.\n"
            "Sarah Johnson: Thanks John. I'm looking forward to this project."
        )
        
        assert chunk.to_transcript_text() == expected_text
    
    def test_vtt_chunk_empty_entries(self):
        """Test VTTChunk with empty entries list."""
        chunk = VTTChunk(
            chunk_id=1,
            entries=[],
            token_count=0
        )
        
        assert chunk.chunk_id == 1
        assert len(chunk.entries) == 0
        assert chunk.token_count == 0
        assert chunk.to_transcript_text() == ""
    
    def test_vtt_chunk_single_entry(self, sample_vtt_entry):
        """Test VTTChunk with single entry."""
        chunk = VTTChunk(
            chunk_id=2,
            entries=[sample_vtt_entry],
            token_count=25
        )
        
        expected_text = "John Smith: Um, so welcome everyone to, uh, the quarterly meeting."
        assert chunk.to_transcript_text() == expected_text
        assert len(chunk.entries) == 1
    
    def test_vtt_chunk_multiple_speakers(self):
        """Test VTTChunk with multiple different speakers."""
        entries = [
            VTTEntry("1", 0.0, 5.0, "Alice", "Hello everyone."),
            VTTEntry("2", 5.0, 10.0, "Bob", "Hi Alice."),
            VTTEntry("3", 10.0, 15.0, "Charlie", "Good morning."),
            VTTEntry("4", 15.0, 20.0, "Alice", "Let's begin."),
        ]
        
        chunk = VTTChunk(
            chunk_id=3,
            entries=entries,
            token_count=50
        )
        
        expected_text = (
            "Alice: Hello everyone.\n"
            "Bob: Hi Alice.\n"
            "Charlie: Good morning.\n"
            "Alice: Let's begin."
        )
        
        assert chunk.to_transcript_text() == expected_text
        
        # Check that all speakers are represented
        speakers = {entry.speaker for entry in chunk.entries}
        assert speakers == {"Alice", "Bob", "Charlie"}
    
    def test_vtt_chunk_with_filler_words(self):
        """Test VTTChunk that contains filler words."""
        entries = [
            VTTEntry("1", 0.0, 5.0, "Speaker1", "Um, so like, we need to, uh, start."),
            VTTEntry("2", 5.0, 10.0, "Speaker2", "Yeah, you know, that's, er, good."),
        ]
        
        chunk = VTTChunk(
            chunk_id=4,
            entries=entries,
            token_count=30
        )
        
        text = chunk.to_transcript_text()
        assert "Um, so like" in text
        assert "Yeah, you know" in text
        assert "uh" in text
        assert "er" in text
    
    def test_vtt_chunk_with_newlines_in_text(self):
        """Test VTTChunk where entry text contains newlines."""
        entries = [
            VTTEntry("1", 0.0, 5.0, "Speaker", "Line one\nLine two"),
            VTTEntry("2", 5.0, 10.0, "Speaker", "Another\nmulti-line\nentry"),
        ]
        
        chunk = VTTChunk(
            chunk_id=5,
            entries=entries,
            token_count=20
        )
        
        text = chunk.to_transcript_text()
        # Should preserve newlines within speaker text but add newlines between speakers
        assert "Speaker: Line one\nLine two\nSpeaker: Another\nmulti-line\nentry" == text
    
    def test_vtt_chunk_high_chunk_id(self):
        """Test VTTChunk with high chunk ID number."""
        chunk = VTTChunk(
            chunk_id=999,
            entries=[VTTEntry("1", 0.0, 1.0, "Speaker", "Test")],
            token_count=5
        )
        
        assert chunk.chunk_id == 999
    
    def test_vtt_chunk_zero_token_count(self, sample_vtt_entries):
        """Test VTTChunk with zero token count."""
        chunk = VTTChunk(
            chunk_id=0,
            entries=sample_vtt_entries,
            token_count=0
        )
        
        assert chunk.token_count == 0
        # Should still generate text even with zero token count
        assert len(chunk.to_transcript_text()) > 0


class TestVTTDataIntegrity:
    """Test data integrity and edge cases for VTT models."""
    
    def test_entry_immutability_concept(self, sample_vtt_entry):
        """Test that VTTEntry behaves as expected for data integrity."""
        original_text = sample_vtt_entry.text
        original_speaker = sample_vtt_entry.speaker
        
        # Entries should maintain their data
        assert sample_vtt_entry.text == original_text
        assert sample_vtt_entry.speaker == original_speaker
    
    def test_chunk_entries_modification(self, sample_vtt_entries):
        """Test that modifying entries list affects chunk."""
        chunk = VTTChunk(
            chunk_id=0,
            entries=sample_vtt_entries.copy(),  # Use copy to avoid side effects
            token_count=100
        )
        
        original_count = len(chunk.entries)
        
        # Modifying the entries list should affect the chunk
        chunk.entries.append(VTTEntry("new", 20.0, 25.0, "New Speaker", "New text"))
        
        assert len(chunk.entries) == original_count + 1
        assert "New Speaker: New text" in chunk.to_transcript_text()
    
    def test_entries_ordering_preservation(self):
        """Test that entry ordering is preserved in chunks."""
        entries = [
            VTTEntry("3", 10.0, 15.0, "Third", "Third speaker"),
            VTTEntry("1", 0.0, 5.0, "First", "First speaker"),
            VTTEntry("2", 5.0, 10.0, "Second", "Second speaker"),
        ]
        
        chunk = VTTChunk(chunk_id=0, entries=entries, token_count=50)
        text = chunk.to_transcript_text()
        
        # Should preserve the order as given, not sort by time
        lines = text.split('\n')
        assert lines[0] == "Third: Third speaker"
        assert lines[1] == "First: First speaker"
        assert lines[2] == "Second: Second speaker"
    
    def test_special_characters_in_speaker_names(self):
        """Test handling of special characters in speaker names."""
        entries = [
            VTTEntry("1", 0.0, 5.0, "O'Connor, Mary", "Hello there."),
            VTTEntry("2", 5.0, 10.0, "Smith-Jones, Bob", "Good morning."),
            VTTEntry("3", 10.0, 15.0, "李小明", "你好."),
        ]
        
        chunk = VTTChunk(chunk_id=0, entries=entries, token_count=30)
        text = chunk.to_transcript_text()
        
        assert "O'Connor, Mary: Hello there." in text
        assert "Smith-Jones, Bob: Good morning." in text
        assert "李小明: 你好." in text
    
    def test_very_long_speaker_name(self):
        """Test handling of very long speaker names."""
        long_name = "Dr. Professor John Michael Smith-Johnson III, PhD, MD, CEO"
        entry = VTTEntry("1", 0.0, 5.0, long_name, "Brief comment.")
        chunk = VTTChunk(chunk_id=0, entries=[entry], token_count=10)
        
        text = chunk.to_transcript_text()
        assert long_name in text
        assert "Brief comment." in text
    
    def test_empty_and_whitespace_text(self):
        """Test handling of empty and whitespace-only text."""
        entries = [
            VTTEntry("1", 0.0, 1.0, "Speaker1", ""),
            VTTEntry("2", 1.0, 2.0, "Speaker2", "   "),
            VTTEntry("3", 2.0, 3.0, "Speaker3", "\t\n"),
            VTTEntry("4", 3.0, 4.0, "Speaker4", "Real text"),
        ]
        
        chunk = VTTChunk(chunk_id=0, entries=entries, token_count=10)
        text = chunk.to_transcript_text()
        
        # All entries should be included, even empty ones
        lines = text.split('\n')
        # Filter out empty lines that might be created by newlines in text
        non_empty_lines = [line for line in lines if line]
        assert len(non_empty_lines) == 4
        assert non_empty_lines[0] == "Speaker1: "
        assert non_empty_lines[1] == "Speaker2:    "
        assert non_empty_lines[2] == "Speaker3: \t"  # Note: split preserves some whitespace
        assert non_empty_lines[3] == "Speaker4: Real text"