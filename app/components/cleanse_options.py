import reflex as rx

from app.state import State


def switch_option(
    label: str, var: rx.Var, on_change: rx.event.EventHandler
) -> rx.Component:
    """A reusable switch component for cleanse options."""
    return rx.el.label(
        rx.el.span(label, class_name="text-sm font-medium text-gray-700"),
        rx.el.div(
            rx.el.input(
                checked=var,
                on_change=on_change,
                type="checkbox",
                class_name="peer sr-only",
            ),
            rx.el.div(
                class_name="peer h-5 w-9 rounded-full bg-gray-300 after:absolute after:start-[2px] after:top-[2px] after:h-4 after:w-4 after:rounded-full after:border after:border-gray-300 after:bg-white after:transition-all after:content-[''] peer-checked:bg-indigo-600 peer-checked:after:translate-x-full peer-checked:after:border-white peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-indigo-300"
            ),
        ),
        class_name="relative inline-flex cursor-pointer items-center justify-between w-full",
    )


def cleanse_options_component() -> rx.Component:
    """Component with switches to control transcript cleansing options."""
    return rx.el.div(
        switch_option(
            "Remove Timestamps",
            State.cleanse_remove_timestamps,
            State.set_cleanse_remove_timestamps,
        ),
        switch_option(
            "Remove Filler Words",
            State.cleanse_remove_fillers,
            State.set_cleanse_remove_fillers,
        ),
        switch_option(
            "Merge Lines", State.cleanse_merge_lines, State.set_cleanse_merge_lines
        ),
        class_name="flex flex-col space-y-3 p-4 bg-gray-50 border border-gray-200 rounded-lg w-64",
    )
