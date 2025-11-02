"""Intelligence extraction workspace."""

from __future__ import annotations

import reflex as rx

from app.components.common import (
    export_section as common_export_section,
    missing_transcript_notice,
)
from app.components.metrics import metric_card
from app.state import (
    ActionItemDisplay,
    KeyAreaDisplay,
    State,
    ValidationDisplay,
)


def intelligence_workspace() -> rx.Component:
    return rx.el.section(
        rx.el.h2("Meeting Intelligence", class_name="text-3xl font-black text-black"),
        rx.el.p(
            "Generate executive summaries, key themes, and action items from the cleaned transcript.",
            class_name="mt-2 text-sm font-bold text-black",
        ),
        rx.cond(
            State.has_transcript,
            rx.el.div(
                cleansed_transcript_section(),
                rx.cond(
                    State.has_intelligence,
                    intelligence_results(),
                    extraction_prompt(),
                ),
                class_name="space-y-8",
            ),
            missing_transcript_notice(
                "No processed transcript available. Upload and process a VTT file to enable intelligence extraction."
            ),
        ),
        class_name="max-w-6xl mx-auto space-y-6",
    )


def extraction_prompt() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.icon("brain", class_name="w-6 h-6 text-black"),
            rx.el.div(
                rx.el.h3(
                    "Extract Meeting Intelligence",
                    class_name="text-lg font-bold text-black",
                ),
                rx.el.p(
                    "Run the intelligence pipeline to generate summaries, key areas, and action items.",
                    class_name="mt-1 text-sm font-medium text-black",
                ),
            ),
            class_name="flex items-start space-x-3",
        ),
        rx.el.ul(
            rx.el.li(
                "📋 Executive summaries", class_name="text-sm font-medium text-black"
            ),
            rx.el.li(
                "🎯 Action items with owners and due dates",
                class_name="text-sm font-medium text-black",
            ),
            rx.el.li(
                "🧩 Key themes with supporting evidence",
                class_name="text-sm font-medium text-black",
            ),
            rx.el.li(
                "✅ Validation notes and unresolved topics",
                class_name="text-sm font-medium text-black",
            ),
            class_name="mt-4 list-disc list-inside space-y-1",
        ),
        rx.cond(
            State.intelligence_running,
            extraction_progress_panel(),
            rx.button(
                "🧠 Extract Intelligence",
                on_click=State.extract_intelligence,
                disabled=State.intelligence_running,
                class_name="mt-5 inline-flex items-center justify-center px-6 py-3 bg-black text-yellow-400 font-bold border-4 border-yellow-400 hover:bg-yellow-400 hover:text-black transition-all",
            ),
        ),
        rx.cond(
            State.intelligence_error != "",
            rx.el.div(
                rx.icon("triangle_alert", class_name="w-4 h-4 mr-2 text-black"),
                rx.el.span(
                    State.intelligence_error, class_name="text-xs font-bold text-black"
                ),
                class_name="mt-4 flex items-center",
            ),
        ),
        class_name="mt-6 p-6 bg-white border-4 border-black space-y-4",
    )


def extraction_progress_panel() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.span(
                "Extraction Status", class_name="text-xs uppercase font-bold text-black"
            ),
            rx.el.div(
                rx.spinner(class_name="w-4 h-4 text-black mr-2"),
                rx.el.p(
                    State.intelligence_status, class_name="text-sm font-bold text-black"
                ),
                class_name="flex items-center",
            ),
            class_name="flex items-center justify-between",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    style={
                        "width": State.intelligence_progress_percent,
                        "background": "#6366f1",
                        "height": "100%",
                        "transition": "width 0.3s ease",
                    },
                ),
                style={
                    "width": "100%",
                    "background": "#e5e7eb",
                    "height": "0.75rem",
                    "borderRadius": "999px",
                    "overflow": "hidden",
                },
            ),
            class_name="mt-3",
        ),
        class_name="mt-5 p-4 border-4 border-black bg-yellow-200",
    )


def intelligence_results() -> rx.Component:
    return rx.el.div(
        intelligence_metrics_header(),
        summary_section(),
        key_areas_section(),
        action_items_section(),
        validation_section(),
        export_section(),
        class_name="space-y-8",
    )


def intelligence_metrics_header() -> rx.Component:
    return rx.el.section(
        rx.el.h3("Pipeline Overview", class_name="text-xl font-black text-black"),
        rx.el.div(
            metric_card("Confidence", State.intelligence_confidence_display),
            metric_card("Key Areas", State.intelligence_key_area_count),
            metric_card("Action Items", State.intelligence_action_item_count),
            metric_card("Processing Time", State.intelligence_processing_time_display),
            class_name="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4",
        ),
        class_name="space-y-2",
    )


def cleansed_transcript_section() -> rx.Component:
    return rx.el.section(
        rx.el.h3("Cleansed Transcript", class_name="text-xl font-black text-black"),
        rx.el.p(
            "Review the cleaned transcript that will be used for intelligence extraction.",
            class_name="mt-1 text-sm font-bold text-black",
        ),
        rx.cond(
            State.cleansed_transcript_text != "",
            rx.el.div(
                rx.el.pre(
                    State.cleansed_transcript_text,
                    class_name="mt-2 whitespace-pre-wrap text-sm leading-relaxed bg-white border-4 border-black px-4 py-3 max-h-96 overflow-y-auto font-mono",
                ),
                class_name="mt-2 p-4 bg-white border-4 border-black",
            ),
            rx.el.div(
                "No cleansed transcript available.",
                class_name="mt-2 p-4 text-sm font-bold text-black bg-cyan-100 border-4 border-black",
            ),
        ),
        class_name="space-y-2",
    )


def summary_section() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.h3("Executive Summary", class_name="text-xl font-black text-black"),
            rx.button(
                rx.icon("refresh_cw", class_name="w-4 h-4 mr-2"),
                "Regenerate Summary",
                on_click=State.extract_intelligence,
                disabled=rx.cond(
                    State.intelligence_running,
                    True,
                    rx.cond(State.has_transcript, False, True),
                ),
                class_name="flex items-center px-4 py-2 text-sm font-bold text-black bg-white border-4 border-black hover:bg-yellow-200 hover:border-yellow-400 disabled:opacity-40 disabled:cursor-not-allowed transition-all",
            ),
            class_name="flex items-center justify-between",
        ),
        rx.cond(
            State.intelligence_running,
            extraction_progress_panel(),
            rx.el.div(
                rx.markdown(
                    State.intelligence_summary_text,
                ),
                class_name="mt-2 p-4 bg-white border-4 border-black prose prose-sm max-w-none",
            ),
        ),
    )


def key_areas_section() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.h3("Key Areas & Themes", class_name="text-xl font-black text-black"),
            rx.el.p(
                "Explore thematic clusters with supporting evidence and follow-up actions.",
                class_name="mt-1 text-sm font-bold text-black",
            ),
        ),
        rx.cond(
            State.intelligence_has_key_areas,
            rx.el.div(
                rx.foreach(State.intelligence_key_area_cards, key_area_card),
                class_name="mt-4 space-y-4",
            ),
            rx.el.div(
                "No key areas were generated for this meeting.",
                class_name="mt-4 text-sm font-bold text-black",
            ),
        ),
        class_name="space-y-2",
    )


def key_area_card(area: KeyAreaDisplay) -> rx.Component:
    highlights_section = rx.cond(
        area["has_highlights"],
        rx.el.div(
            rx.el.span(
                "Highlights", class_name="text-xs font-bold text-black uppercase"
            ),
            rx.el.ul(
                rx.foreach(
                    area["highlights"],
                    lambda highlight, _: rx.el.li(
                        highlight, class_name="text-sm font-medium text-black"
                    ),
                ),
                class_name="mt-2 list-disc list-inside space-y-1",
            ),
            class_name="mt-4",
        ),
        rx.fragment(),
    )

    decisions_section = rx.cond(
        area["has_decisions"],
        rx.el.div(
            rx.el.span(
                "Decisions", class_name="text-xs font-bold text-black uppercase"
            ),
            rx.el.ul(
                rx.foreach(
                    area["decisions"],
                    lambda decision, _: rx.el.li(
                        decision, class_name="text-sm font-medium text-black"
                    ),
                ),
                class_name="mt-2 list-disc list-inside space-y-1",
            ),
            class_name="mt-4",
        ),
        rx.fragment(),
    )

    actions_section = rx.cond(
        area["has_actions"],
        rx.el.div(
            rx.el.span("Actions", class_name="text-xs font-bold text-black uppercase"),
            rx.el.ul(
                rx.foreach(
                    area["actions"],
                    lambda action, _: rx.el.li(
                        action, class_name="text-sm font-medium text-black"
                    ),
                ),
                class_name="mt-2 list-disc list-inside space-y-1",
            ),
            class_name="mt-4",
        ),
        rx.fragment(),
    )

    supporting_section = rx.cond(
        area["has_supporting"],
        rx.el.span(
            area["supporting_text"],
            class_name="mt-3 text-xs font-bold text-black",
        ),
        rx.fragment(),
    )

    return rx.el.div(
        rx.el.div(
            rx.el.h4(area["title"], class_name="text-base font-black text-black"),
            rx.el.span(area["meta"], class_name="text-xs font-bold text-black"),
            class_name="flex flex-col",
        ),
        rx.el.p(area["summary"], class_name="mt-3 text-sm font-medium text-black"),
        highlights_section,
        decisions_section,
        actions_section,
        supporting_section,
        class_name="p-5 bg-white border-4 border-black",
    )


def action_items_section() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.h3("Action Items", class_name="text-xl font-black text-black"),
            rx.el.p(
                "Track owners, due dates, and confidence for each follow-up item.",
                class_name="mt-1 text-sm font-bold text-black",
            ),
        ),
        rx.cond(
            State.intelligence_has_action_items,
            rx.el.div(
                rx.foreach(State.intelligence_action_item_cards, action_item_card),
                class_name="mt-4 grid gap-4 md:grid-cols-2",
            ),
            rx.el.div(
                "No action items were generated for this meeting.",
                class_name="mt-4 text-sm font-bold text-black",
            ),
        ),
        class_name="space-y-2",
    )


def action_item_card(item: ActionItemDisplay) -> rx.Component:
    confidence_section = rx.cond(
        item["has_confidence"],
        rx.el.span(
            item["confidence_text"], class_name="text-xs font-bold text-black mt-3"
        ),
        rx.fragment(),
    )

    return rx.el.div(
        rx.el.h4(item["title"], class_name="text-base font-black text-black"),
        rx.el.div(
            rx.el.span(item["owner_text"], class_name="text-sm font-medium text-black"),
            rx.el.span(item["due_text"], class_name="text-sm font-medium text-black"),
            class_name="flex items-center justify-between mt-2",
        ),
        confidence_section,
        class_name="p-4 bg-white border-4 border-black",
    )


def validation_section() -> rx.Component:
    details: ValidationDisplay = State.intelligence_validation_display

    return rx.el.section(
        rx.el.h3("Validation & Quality", class_name="text-xl font-black text-black"),
        rx.el.div(
            rx.el.span(details["status_label"], class_name=details["status_class"]),
            class_name="inline-flex",
        ),
        rx.cond(
            details["has_issues"],
            rx.el.div(
                rx.el.span(
                    "Detected Issues",
                    class_name="text-xs font-bold text-black uppercase",
                ),
                rx.el.pre(
                    details["issues_text"],
                    class_name="mt-2 whitespace-pre-wrap text-sm font-medium text-black bg-white border-4 border-black px-2 py-2",
                ),
                class_name="mt-4",
            ),
        ),
        rx.cond(
            details["has_unresolved"],
            rx.el.div(
                rx.el.span(
                    "Unresolved Topics",
                    class_name="text-xs font-bold text-black uppercase",
                ),
                rx.el.pre(
                    details["unresolved_text"],
                    class_name="mt-2 whitespace-pre-wrap text-sm font-medium text-black bg-white border-4 border-black px-2 py-2",
                ),
                class_name="mt-4",
            ),
        ),
        rx.cond(
            details["has_notes"],
            rx.el.div(
                rx.el.span(
                    "Validation Notes",
                    class_name="text-xs font-bold text-black uppercase",
                ),
                rx.el.pre(
                    details["notes_text"],
                    class_name="mt-2 whitespace-pre-wrap text-sm font-medium text-black bg-white border-4 border-black px-2 py-2",
                ),
                class_name="mt-4",
            ),
        ),
        class_name="space-y-3",
    )


def export_section() -> rx.Component:
    """Export section for intelligence data."""
    return common_export_section(
        title="Export Intelligence",
        description="Download the intelligence package as Markdown or plain text.",
        formats=[
            ("TXT", "📄", "txt"),
            ("Markdown", "📝", "md"),
        ],
        on_click_handlers={
            "txt": State.download_intelligence("txt"),
            "md": State.download_intelligence("md"),
        },
        disabled_condition=~State.has_intelligence,
        grid_cols="sm:grid-cols-2",
    )
