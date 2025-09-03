"""Standardized metrics display components."""

from typing import Any

import streamlit as st


def render_quality_metrics(quality_data: dict[str, Any]) -> None:
    """Render quality assessment metrics.

    Logic:
    1. Display quality scores and ratings
    2. Show improvement categories
    3. Highlight quality indicators
    """
    if not quality_data:
        return

    st.subheader("🎯 Quality Assessment")

    col1, col2 = st.columns(2)

    with col1:
        overall_quality = quality_data.get("overall_quality_score", 0)
        quality_improvement = quality_data.get("quality_improvement", 0)
        st.metric(
            "Overall Quality",
            f"{overall_quality}/10",
            delta=f"+{quality_improvement:.1f}" if quality_improvement > 0 else None,
        )

    with col2:
        readability = quality_data.get("readability_score", 0)
        st.metric("Readability", f"{readability}/10")

    # Quality categories
    categories = quality_data.get("improvement_categories", [])
    if categories:
        st.caption("**Improvement Categories:**")
        cols = st.columns(len(categories))
        for i, category in enumerate(categories):
            with cols[i]:
                st.success(category)


def render_review_quality_distribution(review_results: list[dict[str, Any]]) -> None:
    """Render quality distribution for review results.

    Logic:
    1. Calculate quality score distribution
    2. Display quality categories with counts
    3. Show acceptance rate metrics
    """
    if not review_results:
        st.info("No review results available")
        return

    st.subheader("🎯 Quality Distribution")

    # Calculate quality metrics
    total_chunks = len(review_results)
    accepted_count = sum(1 for r in review_results if r and r.get("accept", False))
    avg_quality = (
        sum(r.get("quality_score", 0) for r in review_results if r)
        / len(review_results)
        if review_results
        else 0
    )

    # Quality distribution
    quality_scores = [r.get("quality_score", 0) for r in review_results if r]
    high_quality = sum(1 for score in quality_scores if score >= 0.8)
    medium_quality = sum(1 for score in quality_scores if 0.6 <= score < 0.8)
    low_quality = sum(1 for score in quality_scores if score < 0.6)

    # Display metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Chunks", total_chunks)

    with col2:
        acceptance_rate = (
            (accepted_count / total_chunks * 100) if total_chunks > 0 else 0
        )
        st.metric("Accepted", accepted_count, f"{acceptance_rate:.1f}%")

    with col3:
        needs_review = total_chunks - accepted_count
        needs_review_rate = (
            (needs_review / total_chunks * 100) if total_chunks > 0 else 0
        )
        st.metric("Needs Review", needs_review, f"{needs_review_rate:.1f}%")

    with col4:
        quality_status = "Good" if avg_quality > 0.7 else "Needs Review"
        st.metric("Avg Quality", f"{avg_quality:.2f}", quality_status)

    # Quality breakdown
    st.divider()
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "🟢 High Quality (≥0.8)",
            high_quality,
            f"{(high_quality/total_chunks*100):.1f}%" if total_chunks > 0 else "0%",
        )

    with col2:
        st.metric(
            "🟡 Medium Quality (0.6-0.8)",
            medium_quality,
            f"{(medium_quality/total_chunks*100):.1f}%" if total_chunks > 0 else "0%",
        )

    with col3:
        st.metric(
            "🔴 Low Quality (<0.6)",
            low_quality,
            f"{(low_quality/total_chunks*100):.1f}%" if total_chunks > 0 else "0%",
        )


def render_transcript_summary_metrics(transcript_data: dict[str, Any]) -> None:
    """Render basic transcript summary metrics.

    Logic:
    1. Display basic transcript information
    2. Show speaker and duration information
    3. Present entry and chunk counts
    """
    if not transcript_data:
        return

    st.subheader("📊 Processing Summary")

    # Extract basic info
    chunks = transcript_data.get("chunks", [])
    speakers = transcript_data.get("speakers", [])
    duration = transcript_data.get("duration", 0)

    # Calculate total entries
    total_entries = sum(len(chunk.get("entries", [])) for chunk in chunks)

    # Display metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Chunks", len(chunks))

    with col2:
        st.metric("Total Entries", total_entries)

    with col3:
        st.metric("Speakers", len(speakers))

    with col4:
        duration_display = f"{duration:.1f}s"
        duration_help = f"{duration/60:.1f}m" if duration > 60 else None
        st.metric("Duration", duration_display, duration_help)

    # Show speakers
    if speakers:
        st.info(f"**Meeting participants:** {', '.join(speakers)}")


def get_quality_status(score: float) -> tuple[str, str, str]:
    """Get quality status icon, text, and color based on score.

    Logic:
    1. Categorize score into quality levels
    2. Return appropriate icon, text, and color
    3. Used for consistent quality indication
    """
    if score >= 0.8:
        return "✅", "High Quality", "green"
    elif score >= 0.6:
        return "🟡", "Medium Quality", "orange"
    else:
        return "🔴", "Low Quality", "red"
