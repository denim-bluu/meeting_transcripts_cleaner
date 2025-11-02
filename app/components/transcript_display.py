import reflex as rx

from app.components.cleanse_options import cleanse_options_component
from app.state import State


def transcript_entry_card(entry: dict, index: int) -> rx.Component:
    """A card for a single transcript entry."""
    return rx.el.div(
        rx.el.span(
            entry["timestamp"],
            class_name="font-mono text-xs text-indigo-600 bg-indigo-50 px-2 py-1 rounded-md",
        ),
        rx.el.p(entry["text"], class_name="mt-2 text-sm text-gray-700 leading-relaxed"),
        class_name="p-4 bg-white border border-gray-200 rounded-xl shadow-sm hover:shadow-md transition-shadow",
    )


def raw_transcript_view() -> rx.Component:
    """View to display the raw parsed transcript."""
    return rx.el.div(
        rx.el.h3(
            "Raw Transcript", class_name="text-xl font-semibold text-gray-900 mb-4"
        ),
        rx.el.div(
            rx.foreach(
                State.transcript_entries,
                lambda entry, index: transcript_entry_card(entry, index),
            ),
            class_name="space-y-4 max-h-[55vh] overflow-y-auto p-4 bg-gray-50 rounded-lg border",
        ),
        rx.el.div(
            download_button(
                "Download Raw TXT", State.raw_transcript_text, "raw_transcript.txt"
            ),
            class_name="flex justify-end mt-4",
        ),
        class_name="w-full",
    )


def download_button(label: str, content: rx.Var[str], filename: str) -> rx.Component:
    """A button to download content as a text file."""
    return rx.el.button(
        rx.icon("cloud_download", class_name="w-4 h-4 mr-2"),
        label,
        on_click=rx.download(data=content, filename=filename),
        class_name="flex items-center px-3 py-1.5 text-xs font-semibold text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors",
    )


def cleansed_transcript_view() -> rx.Component:
    """View to display the cleansed transcript."""
    return rx.el.div(
        rx.el.div(
            rx.el.h3(
                "Cleansed Transcript", class_name="text-xl font-semibold text-gray-900"
            ),
            class_name="flex justify-between items-center mb-4",
        ),
        rx.el.div(
            rx.el.div(
                cleanse_options_component(),
                rx.el.button(
                    rx.icon("sparkles", class_name="w-4 h-4 mr-2"),
                    "Cleanse Transcript",
                    on_click=State.do_cleanse_transcript,
                    class_name="mt-4 w-full flex items-center justify-center px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-all font-semibold",
                ),
                class_name="w-64",
            ),
            rx.el.div(
                rx.el.pre(
                    State.cleansed_transcript,
                    class_name="whitespace-pre-wrap font-sans text-sm text-gray-800 leading-relaxed p-6 bg-white border border-gray-200 rounded-xl shadow-sm h-full min-h-[40vh] max-h-[55vh] overflow-y-auto",
                ),
                rx.cond(
                    State.has_cleansed_transcript,
                    rx.el.div(
                        download_button(
                            "Download Cleansed TXT",
                            State.cleansed_transcript,
                            "cleansed_transcript.txt",
                        ),
                        class_name="flex justify-end mt-4",
                    ),
                ),
                class_name="flex-1",
            ),
            class_name="flex space-x-6",
        ),
        class_name="w-full",
    )


def ai_summary_view() -> rx.Component:
    """Placeholder for the AI summary view."""
    return rx.el.div(
        rx.el.h3("AI Summary", class_name="text-xl font-semibold text-gray-900 mb-4"),
        rx.cond(
            State.has_cleansed_transcript,
            rx.el.div(
                rx.el.button(
                    rx.icon("brain-circuit", class_name="w-4 h-4 mr-2"),
                    "Generate Summary",
                    class_name="mb-4 flex items-center justify-center px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-all font-semibold",
                ),
                rx.el.div(
                    rx.icon("bot", class_name="w-10 h-10 text-gray-400 mb-4"),
                    rx.el.p(
                        "AI Summary feature is coming soon!", class_name="text-gray-500"
                    ),
                    class_name="flex flex-col items-center justify-center p-12 bg-gray-50 border-2 border-dashed rounded-xl h-full",
                ),
                class_name="w-full h-full flex flex-col",
            ),
            rx.el.div(
                rx.el.p(
                    "Please cleanse the transcript first to enable summary generation.",
                    class_name="text-gray-500 text-center",
                ),
                class_name="flex flex-col items-center justify-center p-12 bg-gray-50 border-2 border-dashed rounded-xl h-full",
            ),
        ),
        class_name="w-full h-full",
    )


def transcript_display_tabs() -> rx.Component:
    """Tabs to switch between raw, cleansed, and summary views."""

    def tab_button(label: str, tab_id: str) -> rx.Component:
        return rx.el.button(
            label,
            on_click=lambda: State.set_active_tab(tab_id),
            class_name=rx.cond(
                State.active_tab == tab_id,
                "px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-lg shadow-md",
                "px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-100 rounded-lg transition-colors",
            ),
        )

    return rx.el.div(
        tab_button("Raw Transcript", "raw"),
        tab_button("Cleansed", "cleansed"),
        tab_button("AI Summary", "summary"),
        class_name="flex items-center space-x-2 p-1 bg-gray-100 rounded-xl w-fit mb-6",
    )


def transcript_display() -> rx.Component:
    """Main component to display transcript data."""
    return rx.el.div(
        transcript_display_tabs(),
        rx.match(
            State.active_tab,
            ("raw", raw_transcript_view()),
            ("cleansed", cleansed_transcript_view()),
            ("summary", ai_summary_view()),
            rx.el.div(),
        ),
        class_name="w-full px-4 md:px-8",
    )
