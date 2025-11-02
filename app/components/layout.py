"""Layout primitives shared across pages."""

import reflex as rx

from app.state import State


def header() -> rx.Component:
    return rx.el.header(
        rx.el.div(
            rx.el.div(
                rx.icon("file-text", class_name="w-8 h-8 text-white"),
                rx.el.div(
                    rx.el.h1(
                        "Meeting Transcript Tool",
                        class_name="text-xl font-bold text-white",
                    ),
                    rx.el.p(
                        "Clean transcripts, review quality, and extract meeting intelligence.",
                        class_name="text-sm text-yellow-200 font-medium",
                    ),
                    class_name="ml-3",
                ),
                class_name="flex items-center",
            ),
            rx.el.nav(
                nav_link("Upload", "/"),
                nav_link("Review", "/review"),
                nav_link("Intelligence", "/intelligence"),
                class_name="flex items-center space-x-6",
            ),
            class_name="container mx-auto px-4 flex items-center justify-between",
        ),
        class_name="bg-black py-4 border-b-4 border-yellow-400",
    )


def nav_link(label: str, href: str) -> rx.Component:
    is_active = State.current_page == href
    active_class = "text-sm font-bold text-yellow-400 border-2 border-yellow-400 px-3 py-1 bg-black"
    inactive_class = "text-sm font-bold text-white hover:text-yellow-400 hover:border-2 hover:border-yellow-400 hover:px-3 hover:py-1 transition-all"

    return rx.link(
        label,
        href=href,
        on_click=State.set_current_page(href),
        class_name=rx.cond(
            is_active,
            active_class,
            inactive_class,
        ),
    )


def page_container(*children: rx.Component) -> rx.Component:
    return rx.el.main(
        header(),
        rx.el.div(
            *children,
            class_name="container mx-auto px-4 py-10",
        ),
        class_name="min-h-screen bg-yellow-50 font-['Montserrat']",
    )
