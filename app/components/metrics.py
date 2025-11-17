"""Metrics visualization components."""

from dash import html

from app.state import (
    get_has_transcript,
    get_transcript_chunk_count,
    get_transcript_total_entries,
    get_transcript_duration_display,
    get_transcript_has_speakers,
    get_transcript_speakers_display,
    get_transcript_acceptance_count,
    get_transcript_acceptance_helper,
    get_transcript_average_quality_display,
    get_transcript_quality_high,
    get_transcript_quality_medium,
    get_transcript_quality_low,
)


def metric_card(title: str, value: str | int | float, helper: str | None = None):
    """Metric card component."""
    elements = [
        html.Span(
            title,
            style={
                "fontSize": "0.75rem",
                "fontWeight": "700",
                "color": "#000000",
                "textTransform": "uppercase",
                "letterSpacing": "0.05em",
            },
        ),
        html.P(
            str(value),
            style={
                "marginTop": "0.25rem",
                "fontSize": "1.875rem",
                "fontWeight": "900",
                "color": "#000000",
            },
        ),
    ]
    if helper is not None:
        elements.append(
            html.Span(
                helper,
                style={
                    "fontSize": "0.75rem",
                    "fontWeight": "700",
                    "color": "#000000",
                    "marginTop": "0.25rem",
                },
            )
        )
    return html.Div(
        elements,
        style={
            "padding": "1rem",
            "backgroundColor": "#ffffff",
            "border": "4px solid #000000",
        },
    )


def transcript_summary_metrics():
    """Summary metrics for transcript processing."""
    if not get_has_transcript():
        return html.Div()

    return html.Div(
        [
            html.H3(
                "Processing Summary",
                style={
                    "fontSize": "1.25rem",
                    "fontWeight": "900",
                    "color": "#000000",
                },
            ),
            html.Div(
                [
                    metric_card("Chunks", get_transcript_chunk_count()),
                    metric_card("Entries", get_transcript_total_entries()),
                    metric_card("Duration", get_transcript_duration_display()),
                ],
                style={
                    "marginTop": "1rem",
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(200px, 1fr))",
                    "gap": "1rem",
                },
            ),
            html.Div(
                [
                    html.Span("👥", style={"marginRight": "0.5rem", "fontSize": "1rem"}),
                    html.Span(
                        get_transcript_speakers_display(),
                        style={"fontSize": "0.875rem", "fontWeight": "700", "color": "#000000"},
                    ),
                ],
                style={
                    "marginTop": "1rem",
                    "display": "inline-flex",
                    "alignItems": "center",
                    "padding": "0.5rem 0.75rem",
                    "backgroundColor": "#67e8f9",
                    "border": "4px solid #000000",
                },
            )
            if get_transcript_has_speakers()
            else html.Div(),
        ],
        style={"marginTop": "2rem"},
    )


def transcript_quality_metrics():
    """Quality metrics for transcript."""
    if not get_has_transcript():
        return html.Div()

    helper_text = get_transcript_acceptance_helper()
    helper = (
        html.Span(
            helper_text,
            style={
                "fontSize": "0.75rem",
                "fontWeight": "700",
                "color": "#000000",
                "marginTop": "0.25rem",
            },
        )
        if helper_text != "—"
        else html.Span(
            "—",
            style={
                "fontSize": "0.75rem",
                "fontWeight": "700",
                "color": "#000000",
                "marginTop": "0.25rem",
            },
        )
    )

    return html.Div(
        [
            html.H3(
                "Quality Overview",
                style={
                    "fontSize": "1.25rem",
                    "fontWeight": "900",
                    "color": "#000000",
                },
            ),
            html.Div(
                [
                    metric_card("Accepted", get_transcript_acceptance_count(), helper),
                    metric_card("Avg Quality", get_transcript_average_quality_display()),
                    metric_card("High Quality", get_transcript_quality_high()),
                    metric_card("Medium Quality", get_transcript_quality_medium()),
                    metric_card("Needs Review", get_transcript_quality_low()),
                ],
                style={
                    "marginTop": "1rem",
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))",
                    "gap": "1rem",
                },
            ),
        ],
        style={"marginTop": "2.5rem"},
    )
