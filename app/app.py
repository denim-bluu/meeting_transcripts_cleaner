import reflex as rx

from app.components.file_upload import upload_panel
from app.components.layout import page_container
from app.components.metrics import (
    transcript_quality_metrics,
    transcript_summary_metrics,
)
from app.state import State

app = rx.App(
    theme=rx.theme(appearance="light"),
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(rel="preconnect", href="https://fonts.gstatic.com", cross_origin=""),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap",
            rel="stylesheet",
        ),
    ],
)


def upload_page() -> rx.Component:
    return page_container(
        rx.el.section(
            rx.el.h2("Upload & Process", class_name="text-3xl font-black text-black text-center"),
            rx.el.p(
                "Upload a VTT transcript to clean, review, and extract meeting intelligence.",
                class_name="mt-2 text-sm font-bold text-black text-center",
            ),
            rx.el.div(
                upload_panel(),
                class_name="flex justify-center",
            ),
            transcript_summary_metrics(),
            transcript_quality_metrics(),
            rx.cond(
                State.processing_complete,
                rx.el.div(
                    rx.el.div(
                        rx.icon("arrow_right", class_name="w-4 h-4 mr-2 text-black"),
                        rx.el.span(
                            "Processing complete. Continue to the review workspace to explore the results.",
                            class_name="text-sm font-bold text-black",
                        ),
                        class_name="flex items-center justify-center",
                    ),
                    rx.el.div(
                        rx.link(
                            rx.el.span("Go to Review", class_name="text-sm font-bold"),
                            href="/review",
                            class_name="mt-3 inline-flex items-center px-6 py-3 bg-black text-yellow-400 font-bold border-4 border-yellow-400 hover:bg-yellow-400 hover:text-black transition-all",
                        ),
                        class_name="flex justify-center",
                    ),
                    class_name="mt-8 p-4 bg-cyan-100 border-4 border-black",
                ),
            ),
            class_name="max-w-5xl mx-auto space-y-6",
        )
    )


def review_page() -> rx.Component:
    from app.components.review import review_workspace

    return page_container(review_workspace())


def intelligence_page() -> rx.Component:
    from app.components.intelligence import intelligence_workspace

    return page_container(intelligence_workspace())


app.add_page(upload_page, route="/", title="Upload & Process")
app.add_page(review_page, route="/review", title="Review")
app.add_page(intelligence_page, route="/intelligence", title="Intelligence")
