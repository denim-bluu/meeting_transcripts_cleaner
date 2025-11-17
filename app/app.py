"""Main Dash application entry point."""

import base64

import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc

from app.components.file_upload import upload_panel
from app.components.intelligence import intelligence_workspace
from app.components.layout import page_container
from app.components.metrics import (
    transcript_quality_metrics,
    transcript_summary_metrics,
)
from app.components.review import review_workspace
from app.state import (
    clear_upload,
    extract_intelligence,
    get_state,
    get_upload_size_display,
    handle_upload,
    start_processing,
)
from shared.utils.exports import generate_export_content
from shared.utils.files import generate_download_filename

# Initialize Dash app with Bootstrap theme
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap",
    ],
    suppress_callback_exceptions=True,
)

# Add custom CSS
app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Meeting Transcript Tool</title>
        {%favicon%}
        {%css%}
        <style>
            body {
                font-family: 'Montserrat', sans-serif;
                background-color: #fefce8;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""

# Store component for client-side state
store = dcc.Store(id="app-store", storage_type="memory", data={})

# Download component
download_component = dcc.Download(id="download-data")

# Location component for routing
location = dcc.Location(id="url", refresh=False)

# Interval component for periodic updates
interval = dcc.Interval(
    id="interval-component",
    interval=500,  # Update every 500ms
    n_intervals=0,
)

# Download buttons that are conditionally rendered but referenced in callbacks
# These need to be in the main layout so Dash recognizes them on all pages at runtime
download_intelligence_buttons = html.Div(
    [
        html.Button("Download TXT", id="download-intelligence-txt", n_clicks=0, style={"display": "none"}),
        html.Button("Download MD", id="download-intelligence-md", n_clicks=0, style={"display": "none"}),
    ]
)

# Main layout
app.layout = html.Div(
    [
        store,
        location,
        interval,
        download_component,
        download_intelligence_buttons,
        html.Div(id="page-content"),
    ]
)

def upload_page():
    """Upload and processing page."""
    return page_container(
        html.Section(
            [
                html.H2(
                    "Upload & Process",
                    className="text-3xl font-black text-black text-center",
                    style={"fontSize": "1.875rem", "fontWeight": "900"},
                ),
                html.P(
                    "Upload a VTT transcript to clean, review, and extract meeting intelligence.",
                    className="mt-2 text-sm font-bold text-black text-center",
                    style={"marginTop": "0.5rem", "fontSize": "0.875rem", "fontWeight": "700"},
                ),
                html.Div(
                    upload_panel(),
                    className="flex justify-center",
                    style={"display": "flex", "justifyContent": "center"},
                ),
                transcript_summary_metrics(),
                transcript_quality_metrics(),
                html.Div(id="processing-complete-message"),
            ],
            className="max-w-5xl mx-auto space-y-6",
            style={"maxWidth": "80rem", "margin": "0 auto"},
        )
    )


def review_page():
    """Review workspace page."""
    return page_container(review_workspace())


def intelligence_page():
    """Intelligence extraction page."""
    return page_container(intelligence_workspace())


# Validation layout ensures all components exist for callback validation
app.validation_layout = html.Div(
    [
        store,
        location,
        interval,
        download_component,
        download_intelligence_buttons,
        upload_page(),
        review_page(),
        intelligence_page(),
    ]
)


# Routing callback
@app.callback(
    Output("page-content", "children"),
    Input("url", "pathname"),
)
def display_page(pathname):
    """Route to appropriate page based on URL."""
    if pathname == "/review":
        return review_page()
    elif pathname == "/intelligence":
        return intelligence_page()
    else:
        return upload_page()


# File upload callback
@app.callback(
    [
        Output("app-store", "data"),
        Output("upload-error", "children"),
        Output("upload-error", "style"),
    ],
    Input("upload-data", "contents"),
    State("upload-data", "filename"),
    State("app-store", "data"),
    prevent_initial_call=True,
)
def handle_file_upload(contents, filename, store_data):
    """Handle file upload."""
    import asyncio

    if contents is None:
        return dash.no_update, "", {"display": "none"}

    # Decode base64 content
    try:
        content_type, content_string = contents.split(",")
        decoded = base64.b64decode(content_string)
        # Try to decode as UTF-8
        content = decoded.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        error_msg = "Unable to decode file. Ensure the file is UTF-8 encoded."
        return dash.no_update, html.Div(
            [
                html.Span("⚠️", style={"marginRight": "0.5rem"}),
                html.Span(error_msg, style={"fontSize": "0.875rem"}),
            ],
            style={
                "marginTop": "1rem",
                "display": "flex",
                "alignItems": "center",
                "padding": "0.75rem",
                "color": "#000000",
                "backgroundColor": "#fca5a5",
                "border": "4px solid #000000",
                "fontWeight": "700",
            },
        ), {"display": "block"}

    # Handle upload asynchronously
    result = asyncio.run(handle_upload(content, filename))

    if not result.get("success"):
        error_msg = result.get("error", "Upload failed")
        return dash.no_update, html.Div(
            [
                html.Span("⚠️", style={"marginRight": "0.5rem"}),
                html.Span(error_msg, style={"fontSize": "0.875rem"}),
            ],
            style={
                "marginTop": "1rem",
                "display": "flex",
                "alignItems": "center",
                "padding": "0.75rem",
                "color": "#000000",
                "backgroundColor": "#fca5a5",
                "border": "4px solid #000000",
                "fontWeight": "700",
            },
        ), {"display": "block"}

    # Update store with new state
    state = get_state()
    new_store = store_data or {}
    new_store.update({
        "uploaded_file_name": state.get("uploaded_file_name", ""),
        "uploaded_file_size": state.get("uploaded_file_size", 0),
        "upload_preview": state.get("upload_preview", ""),
        "upload_preview_truncated": state.get("upload_preview_truncated", False),
        "vtt_content": state.get("vtt_content", ""),
        "processing_status": state.get("processing_status", ""),
    })

    return new_store, "", {"display": "none"}


# Clear upload callback
@app.callback(
    [
        Output("app-store", "data", allow_duplicate=True),
        Output("upload-details", "style", allow_duplicate=True),
    ],
    Input("clear-upload-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_upload_handler(n_clicks):
    """Clear uploaded file."""
    if n_clicks:
        clear_upload()
        return {}, {"display": "none"}
    return dash.no_update, dash.no_update


# Processing callback
@app.callback(
    [
        Output("app-store", "data", allow_duplicate=True),
        Output("processing-status", "children"),
        Output("processing-progress", "style"),
        Output("processing-complete-message", "children"),
    ],
    Input("process-btn", "n_clicks"),
    State("app-store", "data"),
    prevent_initial_call=True,
)
def process_transcript(n_clicks, store_data):
    """Start transcript processing."""
    import asyncio

    if not n_clicks:
        return dash.no_update, "", {"display": "none"}, ""

    state = get_state()
    if not state.get("vtt_content"):
        return dash.no_update, "No file uploaded", {"display": "block"}, ""

    # Run processing asynchronously
    result = asyncio.run(start_processing())

    if not result.get("success"):
        error_msg = result.get("error", "Processing failed")
        return dash.no_update, error_msg, {"display": "block"}, ""

    # Update store
    new_state = get_state()
    new_store = store_data or {}
    new_store.update({
        "transcript_data": new_state.get("transcript_data", {}),
        "processing_complete": new_state.get("processing_complete", False),
        "processing_progress": new_state.get("processing_progress", 0.0),
        "processing_status": new_state.get("processing_status", ""),
    })

    status = new_state.get("processing_status", "")
    complete = new_state.get("processing_complete", False)

    complete_message = ""
    if complete:
        complete_message = html.Div(
            [
                html.Div(
                    [
                        html.Span("→", style={"marginRight": "0.5rem"}),
                        html.Span(
                            "Processing complete. Continue to the review workspace to explore the results.",
                            style={"fontSize": "0.875rem", "fontWeight": "700"},
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center", "justifyContent": "center"},
                ),
                html.Div(
                    dcc.Link(
                        "Go to Review",
                        href="/review",
                        style={
                            "marginTop": "0.75rem",
                            "display": "inline-flex",
                            "alignItems": "center",
                            "padding": "0.75rem 1.5rem",
                            "backgroundColor": "#000000",
                            "color": "#fbbf24",
                            "fontWeight": "700",
                            "border": "4px solid #fbbf24",
                            "textDecoration": "none",
                        },
                    ),
                    style={"display": "flex", "justifyContent": "center"},
                ),
            ],
            style={
                "marginTop": "2rem",
                "padding": "1rem",
                "backgroundColor": "#cffafe",
                "border": "4px solid #000000",
            },
        )

    progress_style = {
        "display": "block" if status else "none",
        "width": "100%",
        "backgroundColor": "#fbbf24",
        "height": "0.75rem",
        "borderRadius": "0px",
        "overflow": "hidden",
    }

    return new_store, status, progress_style, complete_message


# Intelligence extraction callback
@app.callback(
    [
        Output("app-store", "data", allow_duplicate=True),
        Output("intelligence-status", "children"),
        Output("intelligence-progress", "style"),
        Output("intelligence-error", "children"),
        Output("intelligence-error", "style"),
        Output("intelligence-progress-display-container", "style"),
        Output("intelligence-status-display", "children", allow_duplicate=True),
    ],
    Input("extract-intelligence-btn", "n_clicks"),
    State("app-store", "data"),
    prevent_initial_call=True,
)
def extract_intelligence_handler(n_clicks, store_data):
    """Extract intelligence from transcript."""
    import asyncio

    if not n_clicks:
        return dash.no_update, "", {"display": "none"}, "", {"display": "none"}, {"display": "none"}, dash.no_update

    # Run extraction asynchronously
    result = asyncio.run(extract_intelligence())

    if not result.get("success"):
        error_msg = result.get("error", "Extraction failed")
        error_div = html.Div(
            [
                html.Span("⚠️", style={"marginRight": "0.5rem"}),
                html.Span(error_msg, style={"fontSize": "0.75rem", "fontWeight": "700", "color": "#000000"}),
            ],
            style={"display": "flex", "alignItems": "center"},
        )
        return (
            dash.no_update,
            "",
            {"display": "none"},
            error_div,
            {"display": "block"},
            {"display": "none"},
            "",
        )

    # Update store
    new_state = get_state()
    new_store = store_data or {}
    new_store.update({
        "intelligence_data": new_state.get("intelligence_data", {}),
        "intelligence_progress": new_state.get("intelligence_progress", 0.0),
        "intelligence_status": new_state.get("intelligence_status", ""),
        "intelligence_running": new_state.get("intelligence_running", False),
    })

    status = new_state.get("intelligence_status", "")
    progress_style = {
        "display": "block" if status else "none",
        "width": "100%",
        "backgroundColor": "#e5e7eb",
        "height": "0.75rem",
        "borderRadius": "999px",
        "overflow": "hidden",
    }

    # Show progress container if running, hide if complete
    running = new_state.get("intelligence_running", False)
    progress_container_style = {"display": "block"} if running else {"display": "none"}

    return new_store, status, progress_style, "", {"display": "none"}, progress_container_style, status


# Periodic update callback for progress
@app.callback(
    [
        Output("processing-progress-bar", "style"),
    ],
    Input("interval-component", "n_intervals"),
    State("app-store", "data"),
)
def update_progress(n, store_data):
    """Update progress bars periodically."""
    state = get_state()

    processing_progress = state.get("processing_progress", 0.0)

    processing_style = {
        "width": f"{processing_progress * 100:.0f}%",
        "backgroundColor": "#000000",
        "height": "100%",
        "transition": "width 0.3s ease",
        "display": "block" if processing_progress > 0 else "none",
    }

    return (processing_style,)


@app.callback(
    [
        Output("intelligence-progress-bar-inner", "style"),
        Output("intelligence-progress-inner", "style"),
        Output("intelligence-status-display-inner", "children"),
        Output("intelligence-progress-display-container", "style", allow_duplicate=True),
    ],
    Input("intelligence-interval", "n_intervals"),
    prevent_initial_call="initial_duplicate",
)
def update_intelligence_progress(n):
    """Update intelligence progress indicators when on intelligence page."""
    state = get_state()
    progress = state.get("intelligence_progress", 0.0)
    status = state.get("intelligence_status", "")

    bar_style = {
        "width": f"{max(0.0, min(1.0, progress)) * 100:.0f}%",
        "backgroundColor": "#6366f1",
        "height": "100%",
        "transition": "width 0.3s ease",
    }
    track_style = {
        "width": "100%",
        "backgroundColor": "#e5e7eb",
        "height": "0.75rem",
        "borderRadius": "999px",
        "overflow": "hidden",
        "display": "block" if progress > 0 else "none",
    }
    container_style = {
        "marginTop": "1rem",
        "display": "block" if progress > 0 or status else "none",
    }

    return bar_style, track_style, status, container_style


# Sync intelligence status display
@app.callback(
    Output("intelligence-status-display-inner", "children", allow_duplicate=True),
    Input("intelligence-status", "children"),
    prevent_initial_call=True,
)
def sync_intelligence_status_display(status):
    """Sync intelligence status to display element."""
    return status if status else dash.no_update


# Update summary content when intelligence data changes
@app.callback(
    Output("summary-content", "children"),
    Input("app-store", "data"),
)
def update_summary_content(store_data):
    """Update summary content when intelligence data is available."""
    from app.state import get_intelligence_summary_text

    summary_text = get_intelligence_summary_text()

    return html.Div(
        summary_text,
        style={
            "marginTop": "0.5rem",
            "padding": "1rem",
            "backgroundColor": "#ffffff",
            "border": "4px solid #000000",
        },
    )


# Upload details update callback
@app.callback(
    [
        Output("upload-details", "children"),
        Output("upload-details", "style"),
        Output("upload-steps-container", "children"),
    ],
    Input("app-store", "data"),
)
def update_upload_details(store_data):
    """Update upload details display."""
    from app.components.file_upload import upload_steps

    state = get_state()
    has_file = bool(state.get("vtt_content", ""))

    if not has_file:
        return "", {"display": "none"}, upload_steps()

    file_name = state.get("uploaded_file_name", "")
    file_size = get_upload_size_display()
    preview = state.get("upload_preview", "")
    truncated = state.get("upload_preview_truncated", False)

    details = html.Div(
        [
            html.Div(
                [
                    html.H3(
                        "File Details",
                        style={
                            "fontSize": "1rem",
                            "fontWeight": "700",
                            "color": "#000000",
                        },
                    ),
                    html.Button(
                        "✕ Remove",
                        id="clear-upload-btn",
                        n_clicks=0,
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "fontSize": "0.75rem",
                            "fontWeight": "700",
                            "padding": "0.5rem 0.75rem",
                            "backgroundColor": "#fca5a5",
                            "border": "2px solid #000000",
                            "cursor": "pointer",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                },
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                "Filename",
                                style={
                                    "fontSize": "0.75rem",
                                    "color": "#6b7280",
                                    "textTransform": "uppercase",
                                },
                            ),
                            html.P(
                                file_name,
                                style={
                                    "fontWeight": "500",
                                    "fontSize": "0.875rem",
                                    "margin": "0.25rem 0 0 0",
                                },
                            ),
                        ],
                        style={"flex": "1"},
                    ),
                    html.Div(
                        [
                            html.Span(
                                "Size",
                                style={
                                    "fontSize": "0.75rem",
                                    "color": "#6b7280",
                                    "textTransform": "uppercase",
                                },
                            ),
                            html.P(
                                file_size,
                                style={
                                    "fontWeight": "500",
                                    "fontSize": "0.875rem",
                                    "margin": "0.25rem 0 0 0",
                                },
                            ),
                        ],
                        style={"flex": "1"},
                    ),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(2, 1fr)",
                    "gap": "1rem",
                    "marginTop": "1rem",
                },
            ),
            html.Div(
                [
                    html.Span(
                        "Preview",
                        style={
                            "fontSize": "0.75rem",
                            "fontWeight": "700",
                            "color": "#000000",
                            "textTransform": "uppercase",
                        },
                    ),
                    html.Pre(
                        preview,
                        style={
                            "marginTop": "0.5rem",
                            "maxHeight": "12rem",
                            "overflowY": "auto",
                            "whiteSpace": "pre-wrap",
                            "fontSize": "0.875rem",
                            "backgroundColor": "#000000",
                            "color": "#fbbf24",
                            "padding": "0.75rem 1rem",
                            "border": "4px solid #000000",
                            "fontFamily": "monospace",
                        },
                    ),
                    html.Span(
                        "Preview truncated to first 2000 characters.",
                        style={
                            "fontSize": "0.75rem",
                            "fontWeight": "700",
                            "color": "#000000",
                            "marginTop": "0.5rem",
                        },
                    )
                    if truncated
                    else html.Div(),
                ],
                style={"marginTop": "1rem"},
            ),
        ],
        style={
            "marginTop": "1.5rem",
            "padding": "1rem",
            "border": "4px solid #000000",
            "backgroundColor": "#ffffff",
        },
    )

    return details, {"display": "block"}, html.Div()


# Download callbacks
@app.callback(
    Output("download-data", "data"),
    [
        Input("download-transcript-txt", "n_clicks"),
        Input("download-transcript-md", "n_clicks"),
        Input("download-transcript-vtt", "n_clicks"),
        Input("download-intelligence-txt", "n_clicks"),
        Input("download-intelligence-md", "n_clicks"),
    ],
    prevent_initial_call=True,
)
def handle_download(txt_clicks, md_clicks, vtt_clicks, intel_txt_clicks, intel_md_clicks):
    """Handle file downloads."""
    from dash import callback_context

    if not callback_context.triggered:
        return None

    triggered = callback_context.triggered[0]
    button_id = triggered["prop_id"].split(".")[0]
    prop_value = triggered.get("value")

    # Only proceed if button was actually clicked (value must be > 0)
    # This prevents false triggers when buttons are recreated on page navigation
    if not button_id or prop_value is None or prop_value == 0:
        return None

    state = get_state()

    # Determine format and data type
    if "transcript" in button_id:
        data = state.get("transcript_data", {})
        if not data:
            return None
        format_type = button_id.split("-")[-1]
        filename_base = state.get("uploaded_file_name", "transcript.vtt")
        filename = generate_download_filename(filename_base, "cleaned", format_type)
    elif "intelligence" in button_id:
        data = state.get("intelligence_data", {})
        if not data:
            return None
        format_type = button_id.split("-")[-1]
        filename_base = state.get("uploaded_file_name", "transcript.vtt")
        filename = generate_download_filename(filename_base, "intelligence", format_type)
    else:
        return None

    try:
        content, mime_type = generate_export_content(data, format_type)
        # dcc.Download expects content as string or dict with content, filename, type
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        return {"content": str(content), "filename": filename, "type": mime_type}
    except Exception as e:
        import logging
        logging.exception("Download failed: %s", e)
        return None


if __name__ == "__main__":
    app.run(debug=True, port=8050)
