"""Upload and processing components."""

import reflex as rx

from app.state import State


def upload_dropzone() -> rx.Component:
    return rx.upload.root(
        rx.el.div(
            rx.el.div(
                rx.icon("cloud_upload", class_name="w-12 h-12 text-black"),
                rx.el.h3(
                    "Upload VTT File",
                    class_name="mt-4 text-lg font-bold text-black",
                ),
                rx.el.p(
                    "Drag and drop or click to upload your meeting transcript.",
                    class_name="mt-1 text-sm font-medium text-black",
                ),
                rx.el.span(
                    "VTT files only", class_name="mt-2 text-xs font-bold text-black"
                ),
                class_name="flex flex-col items-center justify-center p-8",
            ),
            class_name="w-full border-4 border-dashed border-black cursor-pointer bg-yellow-200 hover:bg-yellow-300 transition-colors",
        ),
        id="vtt-upload",
        on_drop=State.handle_upload(rx.upload_files(upload_id="vtt-upload")),
        accept={"text/vtt": [".vtt"]},
        max_files=1,
    )


def upload_error_banner() -> rx.Component:
    return rx.cond(
        State.upload_error != "",
        rx.el.div(
            rx.icon("triangle_alert", class_name="w-5 h-5 mr-2 text-black"),
            rx.el.p(State.upload_error, class_name="text-sm"),
            class_name="mt-4 flex items-center p-3 text-black bg-red-300 border-4 border-black font-bold",
        ),
    )


def upload_details() -> rx.Component:
    return rx.cond(
        State.has_uploaded_file,
        rx.el.div(
            rx.el.div(
                rx.el.h3(
                    "File Details",
                    class_name="text-base font-bold text-black",
                ),
                rx.el.button(
                    rx.icon("x", class_name="w-4 h-4 mr-1"),
                    "Remove",
                    on_click=State.clear_upload,
                    class_name="flex items-center text-xs font-bold px-3 py-2 bg-red-300 hover:bg-red-400 border-2 border-black",
                ),
                class_name="flex items-center justify-between",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.span("Filename", class_name="text-xs text-gray-500 uppercase"),
                    rx.el.p(State.uploaded_file_name, class_name="font-medium text-sm"),
                    class_name="flex-1",
                ),
                rx.el.div(
                    rx.el.span("Size", class_name="text-xs text-gray-500 uppercase"),
                    rx.el.p(State.upload_size_display, class_name="font-medium text-sm"),
                    class_name="flex-1",
                ),
                class_name="grid grid-cols-2 gap-4 mt-4",
            ),
            rx.el.div(
                rx.el.span("Preview", class_name="text-xs font-bold text-black uppercase"),
                rx.el.pre(
                    State.upload_preview,
                    class_name="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap text-sm bg-black text-yellow-400 px-4 py-3 border-4 border-black font-mono",
                ),
                rx.cond(
                    State.upload_preview_truncated,
                    rx.el.span(
                        "Preview truncated to first 2000 characters.",
                        class_name="text-xs font-bold text-black mt-2",
                    ),
                ),
                class_name="mt-4",
            ),
            class_name="mt-6 p-4 border-4 border-black bg-white",
        ),
    )


def upload_steps() -> rx.Component:
    return rx.el.div(
        rx.el.h3("What happens during processing", class_name="text-base font-bold text-black"),
        rx.el.ul(
            rx.el.li("📤 Upload: File loaded into the app", class_name="text-sm font-medium text-black"),
            rx.el.li("🔧 Parse: VTT parsed and chunked for AI processing", class_name="text-sm font-medium text-black"),
            rx.el.li("🤖 Clean: AI agents clean speech-to-text errors", class_name="text-sm font-medium text-black"),
            rx.el.li("📊 Review: Quality review ensures accuracy", class_name="text-sm font-medium text-black"),
            rx.el.li("✅ Complete: Cleaned transcript ready for review", class_name="text-sm font-medium text-black"),
            class_name="mt-3 space-y-2 list-disc list-inside",
        ),
        class_name="mt-6 p-4 bg-cyan-100 border-4 border-dashed border-black",
    )


def processing_progress_panel() -> rx.Component:
    return rx.cond(
        (State.is_processing) | (State.processing_status != ""),
        rx.el.div(
            rx.el.div(
                rx.el.span("Processing Status", class_name="text-xs uppercase font-bold text-black"),
                rx.el.p(State.processing_status, class_name="text-sm font-bold text-black"),
                class_name="flex items-center justify-between",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        style={
                            "width": State.processing_progress_percent,
                            "background": "#000000",
                            "height": "100%",
                            "transition": "width 0.3s ease",
                        },
                    ),
                    style={
                        "width": "100%",
                        "background": "#fbbf24",
                        "height": "0.75rem",
                        "borderRadius": "0px",
                        "overflow": "hidden",
                    },
                ),
                class_name="mt-3",
            ),
            rx.cond(
                State.transcript_error != "",
                rx.el.div(
                    rx.icon("triangle_alert", class_name="w-4 h-4 mr-2 text-red-600"),
                    rx.el.span(State.transcript_error, class_name="text-xs font-bold text-black"),
                    class_name="mt-3 flex items-start",
                ),
            ),
            class_name="mt-6 p-4 bg-white border-4 border-black",
        ),
    )


def process_action_buttons() -> rx.Component:
    return rx.el.div(
        rx.button(
            "Process VTT File",
            on_click=State.start_processing,
            disabled=State.processing_disabled,
            class_name="w-full justify-center px-6 py-3 bg-black text-yellow-400 font-bold border-4 border-yellow-400 hover:bg-yellow-400 hover:text-black disabled:opacity-40 disabled:cursor-not-allowed transition-all",
        ),
        class_name="mt-6",
    )


def upload_panel() -> rx.Component:
    return rx.el.div(
        upload_dropzone(),
        upload_error_banner(),
        upload_details(),
        process_action_buttons(),
        processing_progress_panel(),
        rx.cond(State.has_uploaded_file, rx.el.div(), upload_steps()),
        class_name="w-full max-w-3xl mx-auto",
    )

