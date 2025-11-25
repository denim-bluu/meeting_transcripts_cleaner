"""Intelligence extraction workspace using Dash Mantine Components."""

from __future__ import annotations

from dash import dcc, html
import dash_mantine_components as dmc

from app.components.common import (
    export_section as common_export_section,
    missing_transcript_notice,
)
from app.components.metrics import metric_card
from app.state import (
    ActionItemDisplay,
    KeyAreaDisplay,
    ValidationDisplay,
    get_cleansed_transcript_text,
    get_intelligence_action_item_cards,
    get_intelligence_action_item_count,
    get_intelligence_confidence_display,
    get_intelligence_has_action_items,
    get_intelligence_has_key_areas,
    get_intelligence_key_area_cards,
    get_intelligence_key_area_count,
    get_intelligence_summary_text,
    get_intelligence_validation_display,
    has_intelligence,
    has_transcript,
)


def intelligence_workspace(data: dict):
    """Main intelligence workspace."""
    if not has_transcript(data):
        return dmc.Container(
            size="xl",
            children=[
                dmc.Title("Meeting Intelligence", order=2),
                dmc.Text(
                    "Generate executive summaries, key themes, and action items from the cleaned transcript.",
                    c="dimmed",
                ),
                missing_transcript_notice(
                    "No processed transcript available. Upload and process a VTT file to enable intelligence extraction."
                ),
            ],
        )

    return dmc.Container(
        size="xl",
        children=[
            dmc.Title("Meeting Intelligence", order=2),
            dmc.Text(
                "Generate executive summaries, key themes, and action items from the cleaned transcript.",
                c="dimmed",
            ),
            dmc.Stack(
                gap="xl",
                mt="xl",
                children=[
                    # Hidden components for callbacks
                    html.Div(id="intelligence-error", style={"display": "none"}),
                    cleansed_transcript_section(data),
                    html.Div(
                        extraction_prompt(data) if not has_intelligence(data) else intelligence_results(data),
                        id="intelligence-content",
                    ),
                ],
            ),
        ],
    )


def extraction_prompt(data: dict):
    """Prompt to extract intelligence."""
    return dmc.Card(
        withBorder=True,
        shadow="sm",
        padding="xl",
        radius="md",
        mt="xl",
        children=[
            dmc.Group(
                align="flex-start",
                gap="md",
                children=[
                    dmc.Text("🧠", size="3rem"),
                    dmc.Stack(
                        gap=5,
                        children=[
                            dmc.Title("Extract Meeting Intelligence", order=3),
                            dmc.Text(
                                "Run the intelligence pipeline to generate summaries, key areas, and action items.",
                                size="sm",
                                c="dimmed",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.List(
                mt="lg",
                spacing="xs",
                children=[
                    dmc.ListItem("📋 Executive summaries"),
                    dmc.ListItem("🎯 Action items with owners and due dates"),
                    dmc.ListItem("🧩 Key themes with supporting evidence"),
                    dmc.ListItem("✅ Validation notes and unresolved topics"),
                ],
            ),
            dmc.Button(
                "🧠 Extract Intelligence",
                id="extract-intelligence-btn",
                size="lg",
                color="dark",
                mt="xl",
                loading=False,
                disabled=False,
            ),
        ],
    )


def intelligence_results(data: dict):
    """Intelligence results display."""
    return dmc.Stack(
        gap="xl",
        children=[
            intelligence_metrics_header(data),
            summary_section(data),
            key_areas_section(data),
            action_items_section(data),
            validation_section(data),
            export_section(data),
        ],
    )


def intelligence_metrics_header(data: dict):
    """Metrics header for intelligence."""
    return dmc.Stack(
        gap="md",
        children=[
            dmc.Title("Pipeline Overview", order=3),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 3},
                spacing="md",
                children=[
                    metric_card("Confidence", get_intelligence_confidence_display(data)),
                    metric_card("Key Areas", get_intelligence_key_area_count(data)),
                    metric_card("Action Items", get_intelligence_action_item_count(data)),
                ],
            ),
        ],
    )


def cleansed_transcript_section(data: dict):
    """Section showing cleansed transcript."""
    text = get_cleansed_transcript_text(data)
    return dmc.Stack(
        gap="xs",
        children=[
            dmc.Title("Cleansed Transcript", order=3),
            dmc.Text(
                "Review the cleaned transcript that will be used for intelligence extraction.",
                c="dimmed",
                size="sm",
            ),
            (
                dmc.ScrollArea(
                    h=300,
                    type="auto",
                    children=[
                        dmc.Code(text, block=True, style={"whiteSpace": "pre-wrap"})
                    ],
                )
                if text
                else dmc.Alert(
                    "No cleansed transcript available.",
                    color="cyan",
                    variant="light",
                )
            ),
        ],
    )


def summary_section(data: dict):
    """Executive summary section."""
    return dmc.Stack(
        gap="md",
        children=[
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Title("Executive Summary", order=3),
                    dmc.Button(
                        "🔄 Regenerate Summary",
                        id="regenerate-summary-btn",
                        variant="outline",
                        color="gray",
                        size="xs",
                    ),
                ],
            ),
            dmc.Paper(
                withBorder=True,
                p="md",
                children=[
                    dcc.Markdown(get_intelligence_summary_text(data))
                ],
            ),
        ],
    )


def key_areas_section(data: dict):
    """Key areas and themes section."""
    if not get_intelligence_has_key_areas(data):
        return dmc.Stack(
            gap="md",
            children=[
                dmc.Title("Key Areas & Themes", order=3),
                dmc.Text(
                    "Explore thematic clusters with supporting evidence and follow-up actions.",
                    c="dimmed",
                    size="sm",
                ),
                dmc.Text("No key areas were generated for this meeting.", fw=700),
            ],
        )

    areas = get_intelligence_key_area_cards(data)
    area_cards = [key_area_card(area) for area in areas]

    return dmc.Stack(
        gap="md",
        children=[
            dmc.Title("Key Areas & Themes", order=3),
            dmc.Text(
                "Explore thematic clusters with supporting evidence and follow-up actions.",
                c="dimmed",
                size="sm",
            ),
            dmc.Stack(gap="md", children=area_cards),
        ],
    )


def key_area_card(area: KeyAreaDisplay):
    """Individual key area card."""
    highlights_section = (
        dmc.Stack(
            gap="xs",
            mt="md",
            children=[
                dmc.Text("Highlights", size="xs", fw=700, tt="uppercase", c="dimmed"),
                dmc.List(
                    size="sm",
                    spacing="xs",
                    children=[
                        dmc.ListItem(highlight)
                        for highlight in area.get("highlights", [])
                    ],
                ),
            ],
        )
        if area.get("has_highlights", False)
        else html.Div()
    )

    decisions_section = (
        dmc.Stack(
            gap="xs",
            mt="md",
            children=[
                dmc.Text("Decisions", size="xs", fw=700, tt="uppercase", c="dimmed"),
                dmc.List(
                    size="sm",
                    spacing="xs",
                    children=[
                        dmc.ListItem(decision)
                        for decision in area.get("decisions", [])
                    ],
                ),
            ],
        )
        if area.get("has_decisions", False)
        else html.Div()
    )

    actions_section = (
        dmc.Stack(
            gap="xs",
            mt="md",
            children=[
                dmc.Text("Actions", size="xs", fw=700, tt="uppercase", c="dimmed"),
                dmc.List(
                    size="sm",
                    spacing="xs",
                    children=[
                        dmc.ListItem(action)
                        for action in area.get("actions", [])
                    ],
                ),
            ],
        )
        if area.get("has_actions", False)
        else html.Div()
    )

    supporting_section = (
        dmc.Text(
            area["supporting_text"],
            size="xs",
            fw=700,
            c="dimmed",
            mt="md",
        )
        if area.get("has_supporting", False)
        else html.Div()
    )

    return dmc.Card(
        withBorder=True,
        padding="lg",
        radius="md",
        children=[
            dmc.Stack(
                gap="xs",
                children=[
                    dmc.Title(area["title"], order=4),
                    dmc.Text(area["meta"], size="xs", fw=700, c="dimmed"),
                ],
            ),
            dmc.Text(area["summary"], size="sm", mt="md"),
            highlights_section,
            decisions_section,
            actions_section,
            supporting_section,
        ],
    )


def action_items_section(data: dict):
    """Action items section."""
    if not get_intelligence_has_action_items(data):
        return dmc.Stack(
            gap="md",
            children=[
                dmc.Title("Action Items", order=3),
                dmc.Text(
                    "Track owners, due dates, and confidence for each follow-up item.",
                    c="dimmed",
                    size="sm",
                ),
                dmc.Text("No action items were generated for this meeting.", fw=700),
            ],
        )

    items = get_intelligence_action_item_cards(data)
    item_cards = [action_item_card(item) for item in items]

    return dmc.Stack(
        gap="md",
        children=[
            dmc.Title("Action Items", order=3),
            dmc.Text(
                "Track owners, due dates, and confidence for each follow-up item.",
                c="dimmed",
                size="sm",
            ),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2},
                spacing="md",
                children=item_cards,
            ),
        ],
    )


def action_item_card(item: ActionItemDisplay):
    """Individual action item card."""
    confidence_section = (
        dmc.Text(
            item["confidence_text"],
            size="xs",
            fw=700,
            c="dimmed",
            mt="md",
        )
        if item.get("has_confidence", False)
        else html.Div()
    )

    return dmc.Card(
        withBorder=True,
        padding="md",
        radius="md",
        children=[
            dmc.Title(item["title"], order=5),
            dmc.Group(
                justify="space-between",
                mt="sm",
                children=[
                    dmc.Text(item["owner_text"], size="sm"),
                    dmc.Text(item["due_text"], size="sm"),
                ],
            ),
            confidence_section,
        ],
    )


def validation_section(data: dict):
    """Validation and quality section."""
    details: ValidationDisplay = get_intelligence_validation_display(data)

    color = "cyan" if "passed" in details["status_label"] else "yellow"

    return dmc.Stack(
        gap="md",
        children=[
            dmc.Title("Validation & Quality", order=3),
            dmc.Badge(
                details["status_label"],
                color=color,
                variant="light",
                size="lg",
            ),
            (
                dmc.Stack(
                    gap="xs",
                    mt="md",
                    children=[
                        dmc.Text("Detected Issues", size="xs", fw=700, tt="uppercase", c="dimmed"),
                        dmc.Code(details["issues_text"], block=True),
                    ],
                )
                if details.get("has_issues", False)
                else html.Div()
            ),
            (
                dmc.Stack(
                    gap="xs",
                    mt="md",
                    children=[
                        dmc.Text("Unresolved Topics", size="xs", fw=700, tt="uppercase", c="dimmed"),
                        dmc.Code(details["unresolved_text"], block=True),
                    ],
                )
                if details.get("has_unresolved", False)
                else html.Div()
            ),
            (
                dmc.Stack(
                    gap="xs",
                    mt="md",
                    children=[
                        dmc.Text("Validation Notes", size="xs", fw=700, tt="uppercase", c="dimmed"),
                        dmc.Code(details["notes_text"], block=True),
                    ],
                )
                if details.get("has_notes", False)
                else html.Div()
            ),
        ],
    )


def export_section(data: dict):
    """Export section for intelligence data."""
    return common_export_section(
        title="Export Intelligence",
        description="Download the intelligence package as Markdown or plain text.",
        formats=[
            ("TXT", "📄", "txt"),
            ("Markdown", "📝", "md"),
        ],
        button_ids={
            "txt": "download-intelligence-txt",
            "md": "download-intelligence-md",
        },
        disabled=not has_intelligence(data),
        grid_cols=2,
    )
