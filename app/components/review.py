"""Review workspace components using Dash Mantine Components."""

from __future__ import annotations

from dash import html
import dash_mantine_components as dmc

from app.components.common import (
    export_section as common_export_section,
    missing_transcript_notice,
)
from app.components.metrics import transcript_quality_metrics
from app.state import (
    ChunkReviewDisplay,
    get_transcript_chunk_pairs,
    get_transcript_has_chunks,
    has_transcript,
)


def review_workspace(data: dict):
    """Main review workspace."""
    if not has_transcript(data):
        return dmc.Container(
            size="xl",
            children=[
                dmc.Title("Review Cleaned Transcript", order=2),
                dmc.Text(
                    "Inspect cleaned chunks, quality scores, and export the transcript in multiple formats.",
                    c="dimmed",
                ),
                missing_transcript_notice(),
            ],
        )

    return dmc.Container(
        size="xl",
        children=[
            dmc.Title("Review Cleaned Transcript", order=2),
            dmc.Text(
                "Inspect cleaned chunks, quality scores, and export the transcript in multiple formats.",
                c="dimmed",
            ),
            review_content(data),
        ],
    )


def review_content(data: dict):
    """Review content with metrics and chunks."""
    return dmc.Stack(
        gap="xl",
        children=[
            transcript_quality_metrics(data),
            chunk_review_panel(data),
            export_section(data),
        ],
    )


def chunk_review_panel(data: dict):
    """Panel displaying chunk reviews."""
    if not get_transcript_has_chunks(data):
        return dmc.Stack(
            gap="md",
            mt="xl",
            children=[
                dmc.Title("Detailed Chunk Review", order=3),
                dmc.Text(
                    "Compare the original transcript with cleaned output and quality scores for each chunk.",
                    c="dimmed",
                    size="sm",
                ),
                dmc.Text("No chunks available to review.", fw=700, mt="md"),
            ],
        )

    pairs = get_transcript_chunk_pairs(data)
    chunk_cards = [chunk_card(pair) for pair in pairs]

    return dmc.Stack(
        gap="md",
        mt="xl",
        children=[
            dmc.Title("Detailed Chunk Review", order=3),
            dmc.Text(
                "Compare the original transcript with cleaned output and quality scores for each chunk.",
                c="dimmed",
                size="sm",
            ),
            dmc.Stack(gap="md", mt="md", children=chunk_cards),
        ],
    )


def chunk_card(pair: ChunkReviewDisplay):
    """Individual chunk review card."""
    confidence_helper = (
        dmc.Text(pair["confidence_text"], size="xs", fw=700, mt=5)
        if pair.get("confidence_text", "") != ""
        else html.Div()
    )

    issues_list = (
        dmc.Alert(
            title="Review Notes",
            color="yellow",
            variant="light",
            mt="md",
            children=[
                dmc.Code(pair["issues_text"], block=True, color="yellow")
            ],
        )
        if pair.get("has_issues", False)
        else html.Div()
    )

    # Determine badge colors based on logic in state.py but mapped to Mantine colors
    quality_color = "cyan" if "High" in pair["quality_label"] else "yellow" if "Medium" in pair["quality_label"] else "red"
    status_color = "cyan" if pair["status_label"] == "Accepted" else "yellow"

    return dmc.Card(
        withBorder=True,
        shadow="sm",
        padding="lg",
        radius="md",
        children=[
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Group(
                        children=[
                            dmc.Text(pair["index_label"], fw=900),
                            dmc.Badge(
                                pair["quality_label"],
                                color=quality_color,
                                variant="light",
                            ),
                            dmc.Text(pair["quality_score"], size="xs", fw=700),
                        ]
                    ),
                    dmc.Badge(
                        pair["status_label"],
                        color=status_color,
                        variant="filled",
                    ),
                ],
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2},
                spacing="md",
                mt="md",
                children=[
                    text_block("Original", pair["original_text"]),
                    text_block("Cleaned", pair["cleaned_text"], helper=confidence_helper),
                ],
            ),
            issues_list,
        ],
    )


def text_block(
    title: str, content: str | dict, helper: html.Div | dmc.Text | None = None
):
    """Text block component for original/cleaned text."""
    return dmc.Stack(
        gap="xs",
        children=[
            dmc.Text(title, size="xs", fw=700, tt="uppercase", c="dimmed"),
            dmc.Paper(
                withBorder=True,
                p="xs",
                bg="gray.0",
                children=[
                    (helper if helper else html.Div()),
                    dmc.Code(str(content), block=True, color="gray", style={"whiteSpace": "pre-wrap"}),
                ],
            ),
        ],
    )


def export_section(data: dict):
    """Export section for cleaned transcript."""
    return common_export_section(
        title="Export Cleaned Transcript",
        description="Download the cleaned transcript in your preferred format.",
        formats=[
            ("TXT", "📄", "txt"),
            ("Markdown", "📝", "md"),
            ("VTT", "🎬", "vtt"),
        ],
        button_ids={
            "txt": "download-transcript-txt",
            "md": "download-transcript-md",
            "vtt": "download-transcript-vtt",
        },
        disabled=not has_transcript(data),
    )
