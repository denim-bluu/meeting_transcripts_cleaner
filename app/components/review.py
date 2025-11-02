"""Review workspace components."""

from __future__ import annotations

import reflex as rx

from app.components.common import (
    export_section as common_export_section,
    missing_transcript_notice,
)
from app.components.metrics import transcript_quality_metrics
from app.state import ChunkReviewDisplay, State


def review_workspace() -> rx.Component:
    return rx.el.section(
        rx.el.h2(
            "Review Cleaned Transcript", class_name="text-3xl font-black text-black"
        ),
        rx.el.p(
            "Inspect cleaned chunks, quality scores, and export the transcript in multiple formats.",
            class_name="mt-2 text-sm font-bold text-black",
        ),
        rx.cond(
            State.has_transcript,
            review_content(),
            missing_transcript_notice(),
        ),
        class_name="max-w-6xl mx-auto space-y-6",
    )


def review_content() -> rx.Component:
    return rx.el.div(
        transcript_quality_metrics(),
        chunk_review_panel(),
        export_section(),
        class_name="space-y-8",
    )


def chunk_review_panel() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.h3(
                "Detailed Chunk Review", class_name="text-xl font-black text-black"
            ),
            rx.el.p(
                "Compare the original transcript with cleaned output and quality scores for each chunk.",
                class_name="mt-1 text-sm font-bold text-black",
            ),
        ),
        rx.cond(
            State.transcript_has_chunks,
            rx.el.div(
                rx.foreach(State.transcript_chunk_pairs, chunk_card),
                class_name="mt-4 space-y-4",
            ),
            rx.el.div(
                "No chunks available to review.",
                class_name="mt-4 text-sm font-bold text-black",
            ),
        ),
        class_name="space-y-4",
    )


def chunk_card(pair: ChunkReviewDisplay) -> rx.Component:
    confidence_helper = rx.cond(
        pair["confidence_text"] != "",
        rx.el.span(
            pair["confidence_text"], class_name="text-xs font-bold text-black mt-1"
        ),
        rx.fragment(),
    )

    issues_list = rx.cond(
        pair["has_issues"],
        rx.el.div(
            rx.el.span(
                "Review Notes", class_name="text-xs font-bold text-black uppercase"
            ),
            rx.el.pre(
                pair["issues_text"],
                class_name="mt-2 whitespace-pre-wrap text-sm font-medium text-black bg-white border-4 border-black px-2 py-2",
            ),
            class_name="mt-4",
        ),
        rx.fragment(),
    )

    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.span(
                    pair["index_label"],
                    class_name="text-sm font-black text-black",
                ),
                rx.el.div(
                    rx.el.span(
                        pair["quality_label"],
                        class_name=pair["quality_badge_class"],
                    ),
                    rx.el.span(
                        pair["quality_score"],
                        class_name="ml-2 text-xs font-bold text-black",
                    ),
                    class_name="inline-flex items-center",
                ),
                class_name="flex items-center space-x-4",
            ),
            rx.el.span(
                pair["status_label"],
                class_name=pair["status_badge_class"],
            ),
            class_name="flex items-center justify-between",
        ),
        rx.el.div(
            text_block("Original", pair["original_text"]),
            text_block("Cleaned", pair["cleaned_text"], helper=confidence_helper),
            class_name="mt-4 grid gap-4 md:grid-cols-2 items-start",
        ),
        issues_list,
        class_name="p-5 bg-white border-4 border-black",
    )


def text_block(
    title: str, content: rx.Var | str, helper: rx.Component | None = None
) -> rx.Component:
    if helper is not None:
        return rx.el.div(
            rx.el.span(title, class_name="text-xs font-bold text-black uppercase"),
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        helper,
                        class_name="mb-2 pb-2 border-b-2 border-black",
                    ),
                    rx.el.pre(
                        content,
                        class_name="whitespace-pre-wrap text-sm leading-relaxed font-mono",
                    ),
                    class_name="bg-yellow-100 border-4 border-black px-4 py-3 max-h-72 overflow-y-auto",
                ),
                class_name="mt-2",
            ),
            class_name="flex flex-col",
        )
    else:
        return rx.el.div(
            rx.el.span(title, class_name="text-xs font-bold text-black uppercase"),
            rx.el.div(
                rx.el.pre(
                    content,
                    class_name="mt-2 whitespace-pre-wrap text-sm leading-relaxed bg-yellow-100 border-4 border-black px-4 py-3 max-h-72 overflow-y-auto font-mono",
                ),
            ),
            class_name="flex flex-col",
        )


def export_section() -> rx.Component:
    """Export section for cleaned transcript."""
    return common_export_section(
        title="Export Cleaned Transcript",
        description="Download the cleaned transcript in your preferred format.",
        formats=[
            ("TXT", "📄", "txt"),
            ("Markdown", "📝", "md"),
            ("VTT", "🎬", "vtt"),
        ],
        on_click_handlers={
            "txt": State.download_transcript("txt"),
            "md": State.download_transcript("md"),
            "vtt": State.download_transcript("vtt"),
        },
        disabled_condition=~State.has_transcript,
    )
