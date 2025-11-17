"""Review workspace components."""

from __future__ import annotations

from dash import html

from app.components.common import (
    export_section as common_export_section,
    missing_transcript_notice,
)
from app.components.metrics import transcript_quality_metrics
from app.state import (
    ChunkReviewDisplay,
    get_has_transcript,
    get_transcript_has_chunks,
    get_transcript_chunk_pairs,
)


def review_workspace():
    """Main review workspace."""
    if not get_has_transcript():
        return html.Section(
            [
                html.H2(
                    "Review Cleaned Transcript",
                    style={
                        "fontSize": "1.875rem",
                        "fontWeight": "900",
                        "color": "#000000",
                    },
                ),
                html.P(
                    "Inspect cleaned chunks, quality scores, and export the transcript in multiple formats.",
                    style={
                        "marginTop": "0.5rem",
                        "fontSize": "0.875rem",
                        "fontWeight": "700",
                        "color": "#000000",
                    },
                ),
                missing_transcript_notice(),
            ],
            style={"maxWidth": "72rem", "margin": "0 auto"},
        )

    return html.Section(
        [
            html.H2(
                "Review Cleaned Transcript",
                style={
                    "fontSize": "1.875rem",
                    "fontWeight": "900",
                    "color": "#000000",
                },
            ),
            html.P(
                "Inspect cleaned chunks, quality scores, and export the transcript in multiple formats.",
                style={
                    "marginTop": "0.5rem",
                    "fontSize": "0.875rem",
                    "fontWeight": "700",
                    "color": "#000000",
                },
            ),
            review_content(),
        ],
        style={"maxWidth": "72rem", "margin": "0 auto"},
    )


def review_content():
    """Review content with metrics and chunks."""
    return html.Div(
        [
            transcript_quality_metrics(),
            chunk_review_panel(),
            export_section(),
        ],
        style={"display": "flex", "flexDirection": "column", "gap": "2rem"},
    )


def chunk_review_panel():
    """Panel displaying chunk reviews."""
    if not get_transcript_has_chunks():
        return html.Section(
            [
                html.Div(
                    [
                        html.H3(
                            "Detailed Chunk Review",
                            style={
                                "fontSize": "1.25rem",
                                "fontWeight": "900",
                                "color": "#000000",
                            },
                        ),
                        html.P(
                            "Compare the original transcript with cleaned output and quality scores for each chunk.",
                            style={
                                "marginTop": "0.25rem",
                                "fontSize": "0.875rem",
                                "fontWeight": "700",
                                "color": "#000000",
                            },
                        ),
                    ]
                ),
                html.Div(
                    "No chunks available to review.",
                    style={
                        "marginTop": "1rem",
                        "fontSize": "0.875rem",
                        "fontWeight": "700",
                        "color": "#000000",
                    },
                ),
            ],
            style={"display": "flex", "flexDirection": "column", "gap": "1rem"},
        )

    pairs = get_transcript_chunk_pairs()
    chunk_cards = [chunk_card(pair) for pair in pairs]

    return html.Section(
        [
            html.Div(
                [
                    html.H3(
                        "Detailed Chunk Review",
                        style={
                            "fontSize": "1.25rem",
                            "fontWeight": "900",
                            "color": "#000000",
                        },
                    ),
                    html.P(
                        "Compare the original transcript with cleaned output and quality scores for each chunk.",
                        style={
                            "marginTop": "0.25rem",
                            "fontSize": "0.875rem",
                            "fontWeight": "700",
                            "color": "#000000",
                        },
                    ),
                ]
            ),
            html.Div(
                chunk_cards,
                style={"marginTop": "1rem", "display": "flex", "flexDirection": "column", "gap": "1rem"},
            ),
        ],
        style={"display": "flex", "flexDirection": "column", "gap": "1rem"},
    )


def chunk_card(pair: ChunkReviewDisplay):
    """Individual chunk review card."""
    confidence_helper = (
        html.Span(
            pair["confidence_text"],
            style={
                "fontSize": "0.75rem",
                "fontWeight": "700",
                "color": "#000000",
                "marginTop": "0.25rem",
            },
        )
        if pair.get("confidence_text", "") != ""
        else html.Div()
    )

    issues_list = (
        html.Div(
            [
                html.Span(
                    "Review Notes",
                    style={
                        "fontSize": "0.75rem",
                        "fontWeight": "700",
                        "color": "#000000",
                        "textTransform": "uppercase",
                    },
                ),
                html.Pre(
                    pair["issues_text"],
                    style={
                        "marginTop": "0.5rem",
                        "whiteSpace": "pre-wrap",
                        "fontSize": "0.875rem",
                        "fontWeight": "500",
                        "color": "#000000",
                        "backgroundColor": "#ffffff",
                        "border": "4px solid #000000",
                        "padding": "0.5rem",
                    },
                ),
            ],
            style={"marginTop": "1rem"},
        )
        if pair.get("has_issues", False)
        else html.Div()
    )

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                pair["index_label"],
                                style={
                                    "fontSize": "0.875rem",
                                    "fontWeight": "900",
                                    "color": "#000000",
                                },
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        pair["quality_label"],
                                        className=pair["quality_badge_class"],
                                        style={
                                            "fontSize": "0.75rem",
                                            "fontWeight": "700",
                                            "padding": "0.25rem 0.5rem",
                                            "border": "2px solid #000000",
                                        },
                                    ),
                                    html.Span(
                                        pair["quality_score"],
                                        style={
                                            "marginLeft": "0.5rem",
                                            "fontSize": "0.75rem",
                                            "fontWeight": "700",
                                            "color": "#000000",
                                        },
                                    ),
                                ],
                                style={"display": "inline-flex", "alignItems": "center"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "gap": "1rem"},
                    ),
                    html.Span(
                        pair["status_label"],
                        className=pair["status_badge_class"],
                        style={
                            "fontSize": "0.75rem",
                            "fontWeight": "700",
                            "padding": "0.25rem 0.75rem",
                            "border": "2px solid #000000",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                },
            ),
            html.Div(
                [
                    text_block("Original", pair["original_text"]),
                    text_block("Cleaned", pair["cleaned_text"], helper=confidence_helper),
                ],
                style={
                    "marginTop": "1rem",
                    "display": "grid",
                    "gridTemplateColumns": "repeat(2, 1fr)",
                    "gap": "1rem",
                    "alignItems": "start",
                },
            ),
            issues_list,
        ],
        style={
            "padding": "1.25rem",
            "backgroundColor": "#ffffff",
            "border": "4px solid #000000",
        },
    )


def text_block(
    title: str, content: str | dict, helper: html.Div | None = None
):
    """Text block component for original/cleaned text."""
    if helper is not None:
        return html.Div(
            [
                html.Span(
                    title,
                    style={
                        "fontSize": "0.75rem",
                        "fontWeight": "700",
                        "color": "#000000",
                        "textTransform": "uppercase",
                    },
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                helper,
                                html.Pre(
                                    str(content),
                                    style={
                                        "whiteSpace": "pre-wrap",
                                        "fontSize": "0.875rem",
                                        "lineHeight": "1.75",
                                        "fontFamily": "monospace",
                                    },
                                ),
                            ],
                            style={
                                "backgroundColor": "#fef08a",
                                "border": "4px solid #000000",
                                "padding": "0.75rem 1rem",
                                "maxHeight": "18rem",
                                "overflowY": "auto",
                            },
                        ),
                    ],
                    style={"marginTop": "0.5rem"},
                ),
            ],
            style={"display": "flex", "flexDirection": "column"},
        )
    else:
        return html.Div(
            [
                html.Span(
                    title,
                    style={
                        "fontSize": "0.75rem",
                        "fontWeight": "700",
                        "color": "#000000",
                        "textTransform": "uppercase",
                    },
                ),
                html.Div(
                    html.Pre(
                        str(content),
                        style={
                            "marginTop": "0.5rem",
                            "whiteSpace": "pre-wrap",
                            "fontSize": "0.875rem",
                            "lineHeight": "1.75",
                            "backgroundColor": "#fef08a",
                            "border": "4px solid #000000",
                            "padding": "0.75rem 1rem",
                            "maxHeight": "18rem",
                            "overflowY": "auto",
                            "fontFamily": "monospace",
                        },
                    ),
                ),
            ],
            style={"display": "flex", "flexDirection": "column"},
        )


def export_section():
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
        disabled=not get_has_transcript(),
    )
