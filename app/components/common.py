"""Common reusable UI components."""

from __future__ import annotations

import reflex as rx

from app.state import State


def missing_transcript_notice(message: str = "") -> rx.Component:
    """Notice shown when no transcript is available.

    Args:
        message: Custom message (optional)
    """
    default_message = (
        "No processed transcript available. Upload and process a VTT file first."
    )
    return rx.el.div(
        rx.icon("triangle_alert", class_name="w-5 h-5 text-black mr-2 flex-shrink-0"),
        rx.el.div(
            rx.el.p(
                message or default_message,
                class_name="text-sm font-bold text-black mb-3",
            ),
            rx.link(
                "Go to Upload",
                href="/",
                class_name="inline-flex w-fit items-center px-6 py-3 bg-black text-yellow-400 font-bold border-4 border-yellow-400 hover:bg-yellow-400 hover:text-black transition-all",
            ),
            class_name="flex-1 flex flex-col",
        ),
        class_name="mt-6 flex items-start space-x-3 p-4 bg-yellow-200 border-4 border-black",
    )


def export_button(
    label: str,
    icon: str,
    format_type: str,
    on_click_handler: rx.event.EventHandler,
    disabled_condition: rx.Var[bool],
    class_name: str = "w-full justify-center px-4 py-2 bg-white border-4 border-black text-sm font-bold text-black hover:bg-yellow-200 disabled:opacity-40 transition-all",
) -> rx.Component:
    """Generic export button component.

    Args:
        label: Button label (e.g., "TXT", "Markdown")
        icon: Icon emoji or name
        format_type: Format identifier (e.g., "txt", "md")
        on_click_handler: Event handler for click
        disabled_condition: Condition to disable button
        class_name: CSS classes
    """
    return rx.button(
        f"{icon} Download {label}",
        on_click=on_click_handler,
        disabled=disabled_condition,
        class_name=class_name,
    )


def export_section(
    title: str,
    description: str,
    formats: list[tuple[str, str, str]],
    on_click_handlers: dict[str, rx.event.EventHandler],
    disabled_condition: rx.Var[bool],
    grid_cols: str = "sm:grid-cols-3",
) -> rx.Component:
    """Generic export section component.

    Args:
        title: Section title
        description: Section description
        formats: List of (label, icon, format_type) tuples
        on_click_handlers: Dict mapping format_type to handler
        disabled_condition: Condition to disable buttons
        grid_cols: Grid column classes
    """
    return rx.el.section(
        rx.el.h3(title, class_name="text-xl font-black text-black"),
        rx.el.p(description, class_name="mt-1 text-sm font-bold text-black"),
        rx.el.div(
            *[
                export_button(
                    label=label,
                    icon=icon,
                    format_type=format_type,
                    on_click_handler=on_click_handlers[format_type],
                    disabled_condition=disabled_condition,
                )
                for label, icon, format_type in formats
            ],
            class_name=f"mt-4 grid gap-3 {grid_cols}",
        ),
        rx.cond(
            State.last_download_error != "",
            rx.el.div(
                rx.icon("triangle_alert", class_name="w-4 h-4 mr-2 text-black"),
                rx.el.span(
                    State.last_download_error,
                    class_name="text-xs font-bold text-black",
                ),
                class_name="mt-3 flex items-center",
            ),
        ),
        class_name="space-y-2",
    )
