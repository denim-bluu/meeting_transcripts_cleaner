"""Metrics visualization components."""

import reflex as rx

from app.state import State


def metric_card(
    title: str, value: rx.Var | str, helper: rx.Component | None = None
) -> rx.Component:
    elements: list[rx.Component] = [
        rx.el.span(
            title, class_name="text-xs font-bold text-black uppercase tracking-wide"
        ),
        rx.el.p(value, class_name="mt-1 text-3xl font-black text-black"),
    ]
    if helper is not None:
        elements.append(helper)
    return rx.el.div(
        *elements,
        class_name="p-4 bg-white border-4 border-black",
    )


def transcript_summary_metrics() -> rx.Component:
    return rx.cond(
        State.has_transcript,
        rx.el.div(
            rx.el.h3("Processing Summary", class_name="text-xl font-black text-black"),
            rx.el.div(
                metric_card("Chunks", State.transcript_chunk_count),
                metric_card("Entries", State.transcript_total_entries),
                metric_card("Duration", State.transcript_duration_display),
                class_name="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
            ),
            rx.cond(
                State.transcript_has_speakers,
                rx.el.div(
                    rx.icon("users", class_name="w-4 h-4 mr-2 text-black"),
                    rx.el.span(
                        State.transcript_speakers_display,
                        class_name="text-sm font-bold text-black",
                    ),
                    class_name="mt-4 inline-flex items-center px-3 py-2 bg-cyan-300 border-4 border-black",
                ),
            ),
            class_name="mt-8",
        ),
    )


def transcript_quality_metrics() -> rx.Component:
    return rx.cond(
        State.has_transcript,
        rx.el.div(
            rx.el.h3("Quality Overview", class_name="text-xl font-black text-black"),
            rx.el.div(
                metric_card(
                    "Accepted",
                    State.transcript_acceptance_count,
                    helper=rx.cond(
                        State.transcript_acceptance_helper != "—",
                        rx.el.span(
                            State.transcript_acceptance_helper,
                            class_name="text-xs font-bold text-black mt-1",
                        ),
                        rx.el.span("—", class_name="text-xs font-bold text-black mt-1"),
                    ),
                ),
                metric_card(
                    "Avg Quality",
                    State.transcript_average_quality_display,
                ),
                metric_card(
                    "High Quality",
                    State.transcript_quality_high,
                ),
                metric_card(
                    "Medium Quality",
                    State.transcript_quality_medium,
                ),
                metric_card(
                    "Needs Review",
                    State.transcript_quality_low,
                ),
                class_name="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4",
            ),
            class_name="mt-10",
        ),
    )
