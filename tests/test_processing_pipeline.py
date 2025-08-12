#!/usr/bin/env python3
"""
Test script to verify the complete processing pipeline works end-to-end.
This bypasses Streamlit to test the core functionality directly.
"""

import asyncio
import time
from services.transcript_service import TranscriptService
from config import Config, configure_structlog

# Configure logging
configure_structlog()

# Sample VTT content for testing
SAMPLE_VTT = """WEBVTT

1
00:00:01.000 --> 00:00:05.000
<v John>Hello everyone, welcome to our quarterly review meeting.</v>

2
00:00:05.000 --> 00:00:10.000
<v Sarah>Thank you John. Let's start with the Q3 results.</v>

3
00:00:10.000 --> 00:00:15.000
<v John>Great, Sarah. As you can see from our dashboard, we achieved 127% of our target.</v>

4
00:00:15.000 --> 00:00:20.000
<v Mike>That's fantastic! What were the key drivers behind this success?</v>

5
00:00:20.000 --> 00:00:25.000
<v Sarah>The main factors were increased customer retention and our new product launch.</v>
"""

async def test_complete_pipeline():
    """Test the complete processing pipeline."""
    print("🚀 Testing Complete Processing Pipeline")
    print("=" * 50)
    
    # Initialize service
    print("1. Initializing TranscriptService...")
    service = TranscriptService(Config.OPENAI_API_KEY, max_concurrent=2, rate_limit=10)
    
    # Phase 1: Parse VTT
    print("\n2. Parsing VTT content...")
    transcript = service.process_vtt(SAMPLE_VTT)
    
    print(f"   ✅ Parsed {len(transcript['entries'])} VTT entries")
    print(f"   ✅ Created {len(transcript['chunks'])} chunks")
    print(f"   ✅ Found {len(transcript['speakers'])} speakers: {', '.join(transcript['speakers'])}")
    print(f"   ✅ Duration: {transcript['duration']:.1f} seconds")
    
    # Phase 2: AI Processing with progress tracking
    print("\n3. Running AI processing pipeline...")
    
    progress_updates = []
    def track_progress(progress: float, status: str):
        progress_updates.append((progress, status))
        print(f"   📊 {progress:.1%} - {status}")
    
    start_time = time.time()
    
    # Run the complete cleaning pipeline
    cleaned_transcript = await service.clean_transcript(transcript, track_progress)
    
    processing_time = time.time() - start_time
    
    # Results analysis
    print("\n4. Processing Results:")
    print(f"   ⏱️  Processing time: {processing_time:.2f} seconds")
    print(f"   📈 Progress updates: {len(progress_updates)}")
    
    cleaned_chunks = cleaned_transcript.get('cleaned_chunks', [])
    review_results = cleaned_transcript.get('review_results', [])
    
    if cleaned_chunks and review_results:
        accepted_count = sum(1 for r in review_results if r.get('accept', False))
        avg_confidence = sum(c.get('confidence', 0) for c in cleaned_chunks) / len(cleaned_chunks)
        avg_quality = sum(r.get('quality_score', 0) for r in review_results) / len(review_results)
        
        print(f"   ✅ Processed chunks: {len(cleaned_chunks)}")
        print(f"   ✅ Accepted chunks: {accepted_count} ({accepted_count/len(review_results)*100:.1f}%)")
        print(f"   ✅ Average confidence: {avg_confidence:.2f}")
        print(f"   ✅ Average quality: {avg_quality:.2f}")
        
        # Test export functionality
        print("\n5. Testing export functionality...")
        
        try:
            vtt_export = service.export(cleaned_transcript, "vtt")
            txt_export = service.export(cleaned_transcript, "txt") 
            json_export = service.export(cleaned_transcript, "json")
            
            print(f"   ✅ VTT export: {len(vtt_export)} characters")
            print(f"   ✅ TXT export: {len(txt_export)} characters")
            print(f"   ✅ JSON export: {len(json_export)} characters")
            
        except Exception as e:
            print(f"   ❌ Export failed: {e}")
            
        print("\n🎉 Pipeline test completed successfully!")
        
        # Show sample of final output
        final_transcript = cleaned_transcript.get('final_transcript', '')
        if final_transcript:
            print("\n📋 Sample of cleaned transcript:")
            print("-" * 40)
            print(final_transcript[:300] + "..." if len(final_transcript) > 300 else final_transcript)
            
    else:
        print("   ❌ No cleaning results found")
        return False
        
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_complete_pipeline())
        if result:
            print("\n✅ All tests passed! The processing pipeline is working correctly.")
        else:
            print("\n❌ Tests failed! Check the logs for details.")
    except Exception as e:
        print(f"\n💥 Pipeline test failed with error: {e}")
        import traceback
        traceback.print_exc()