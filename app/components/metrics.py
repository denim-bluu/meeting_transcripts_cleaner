"""Metrics visualization components using Dash Mantine Components."""

from dash import html
import dash_mantine_components as dmc

from app.state import (
    has_transcript,
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
    return dmc.Card(
        withBorder=True,
        padding="md",
        radius="md",
        children=[
            dmc.Text(title, size="xs", fw=700, tt="uppercase", c="dimmed"),
            dmc.Text(str(value), size="xl", fw=900, mt=5),
            (
                dmc.Text(helper, size="xs", fw=700, c="dimmed", mt=5)
                if helper
                else html.Div()
            ),
        ],
    )


def transcript_summary_metrics(data: dict):
    """Summary metrics for transcript processing."""
    if not has_transcript(data):
        return html.Div()

    return dmc.Stack(
        gap="xs",
        mt="xl",
        children=[
            dmc.Title("Processing Summary", order=3),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 3},
                spacing="md",
                children=[
                    metric_card("Chunks", get_transcript_chunk_count(data)),
                    metric_card("Entries", get_transcript_total_entries(data)),
                    metric_card("Duration", get_transcript_duration_display(data)),
                ],
            ),
            (
                dmc.Group(
                    gap="xs",
                    mt="md",
                    children=[
                        dmc.Text("👥", size="lg"),
                        dmc.Badge(
                            get_transcript_speakers_display(data),
                            variant="light",
                            color="cyan",
                            size="lg",
                        ),
                    ],
                )
                if get_transcript_has_speakers(data)
                else html.Div()
            ),
        ],
    )


def transcript_quality_metrics(data: dict):
    """Quality metrics for transcript."""
    if not has_transcript(data):
        return html.Div()

    helper_text = get_transcript_acceptance_helper(data)
    
    return dmc.Stack(
        gap="xs",
        mt="xl",
        children=[
            dmc.Title("Quality Overview", order=3),
            dmc.SimpleGrid(
                cols={"base": 2, "md": 3, "lg": 5},
                spacing="md",
                children=[
                    metric_card("Accepted", get_transcript_acceptance_count(data), helper_text),
                    metric_card("Avg Quality", get_transcript_average_quality_display(data)),
                    metric_card("High Quality", get_transcript_quality_high(data)),
                    metric_card("Medium Quality", get_transcript_quality_medium(data)),
                    metric_card("Needs Review", get_transcript_quality_low(data)),
                ],
            ),
        ],
    )
