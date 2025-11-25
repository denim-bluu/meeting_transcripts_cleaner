"""Main Dash application entry point."""

import base64

import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from app.components.file_upload import upload_panel, upload_steps
from app.components.intelligence import intelligence_workspace
from app.components.layout import page_container
from app.components.metrics import (
    transcript_quality_metrics,
    transcript_summary_metrics,
)
from app.components.review import review_workspace
from app.state import (
    clear_upload_state,
    extract_intelligence,
    get_default_state,
    get_intelligence_summary_text,
    get_upload_size_display,
    handle_upload,
    has_intelligence,
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
    assets_folder="assets",
)

# Store component for client-side state
store = dcc.Store(id="app-store", storage_type="memory", data=get_default_state())

# Download component
download_component = dcc.Download(id="download-data")

# Location component for routing
location = dcc.Location(id="url", refresh=False)

# Main layout
app.layout = dmc.MantineProvider(
    html.Div(
        [
            store,
            location,
            download_component,
            html.Div(id="page-content"),
        ]
    )
)


def upload_page(data: dict):
    """Upload and processing page."""
    return page_container(
        html.Section(
            [
                html.H2(
                    "Upload & Process",
                    className="page-title",
                    style={"textAlign": "center"},
                ),
                html.P(
                    "Upload a VTT transcript to clean, review, and extract meeting intelligence.",
                    className="subtitle",
                    style={"textAlign": "center"},
                ),
                html.Div(
                    upload_panel(),
                    className="flex-center",
                ),
                transcript_summary_metrics(data),
                transcript_quality_metrics(data),
                html.Div(id="processing-complete-message"),
            ],
            className="page-container",
            style={"maxWidth": "80rem"},
        )
    )


def review_page(data: dict):
    """Review workspace page."""
    return page_container(review_workspace(data))


def intelligence_page(data: dict):
    """Intelligence extraction page."""
    return page_container(intelligence_workspace(data))


# Validation layout ensures all components exist for callback validation
app.validation_layout = html.Div(
    [
        store,
        location,
        download_component,
        upload_page(get_default_state()),
        review_page(get_default_state()),
        intelligence_page(get_default_state()),
    ]
)


# Routing callback
@app.callback(
    Output("page-content", "children"),
    [Input("url", "pathname"), Input("app-store", "data")],
)
def display_page(pathname, store_data):
    """Route to appropriate page based on URL."""
    data = store_data or get_default_state()
    if pathname == "/review":
        return review_page(data)
    elif pathname == "/intelligence":
        return intelligence_page(data)
    else:
        return upload_page(data)


# File upload callback
@app.callback(
    [
        Output("app-store", "data", allow_duplicate=True),
        Output("upload-error", "children"),
        Output("upload-error", "style"),
    ],
    Input("upload-data", "contents"),
    [State("upload-data", "filename"), State("app-store", "data")],
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
        return dash.no_update, dmc.Alert(
            error_msg,
            title="Upload Error",
            color="red",
            variant="light",
            withCloseButton=True
        ), {"display": "block"}

    # Handle upload asynchronously
    current_state = store_data or get_default_state()
    result = asyncio.run(handle_upload(content, filename, current_state))

    if not result.get("success"):
        error_msg = result.get("error", "Upload failed")
        return dash.no_update, dmc.Alert(
            error_msg,
            title="Upload Failed",
            color="red",
            variant="light",
            withCloseButton=True
        ), {"display": "block"}

    # Update store with new state (remove success/error keys from result)
    new_store = store_data or get_default_state()
    updates = {k: v for k, v in result.items() if k not in ("success", "error")}
    new_store.update(updates)

    return new_store, "", {"display": "none"}


# Clear upload callback
@app.callback(
    [
        Output("app-store", "data", allow_duplicate=True),
        Output("upload-details", "style", allow_duplicate=True),
    ],
    Input("clear-upload-btn", "n_clicks"),
    State("app-store", "data"),
    prevent_initial_call=True,
)
def clear_upload_handler(n_clicks, store_data):
    """Clear uploaded file."""
    if n_clicks:
        current_state = store_data or get_default_state()
        updates = clear_upload_state()
        new_state = current_state.copy()
        new_state.update(updates)
        return new_state, {"display": "none"}
    return dash.no_update, dash.no_update


# Processing callback
@app.callback(
    [
        Output("app-store", "data", allow_duplicate=True),
        Output("processing-complete-message", "children"),
    ],
    Input("process-btn", "n_clicks"),
    State("app-store", "data"),
    prevent_initial_call=True,
    running=[
        (Output("process-btn", "loading"), True, False),
    ],
)
def process_transcript(n_clicks, store_data):
    """Start transcript processing."""
    import asyncio

    if not n_clicks:
        return dash.no_update, ""

    current_state = store_data or get_default_state()
    vtt_content = current_state.get("vtt_content", "")
    if not vtt_content:
        return dash.no_update, ""

    # Run processing asynchronously
    result = asyncio.run(start_processing(vtt_content, current_state))

    if not result.get("success"):
        error_msg = result.get("error", "Processing failed")
        # Update store with error state
        new_state = current_state.copy()
        new_state.update({
            "transcript_error": error_msg,
            "is_processing": False,
            "processing_status": "",
            "processing_progress": 0.0,
        })
        return new_state, ""

    # Update store with results
    new_state = current_state.copy()
    updates = {k: v for k, v in result.items() if k not in ("success", "error", "data")}
    new_state.update(updates)

    complete = new_state.get("processing_complete", False)

    complete_message = ""
    if complete:
        complete_message = dmc.Alert(
            children=[
                dmc.Group(
                    children=[
                        dmc.Text("Processing complete. Continue to the review workspace to explore the results."),
                        dcc.Link(
                            dmc.Button(
                                "Go to Review",
                                variant="outline",
                                color="blue",
                                size="xs",
                            ),
                            href="/review",
                        ),
                    ],
                    justify="space-between",
                )
            ],
            title="Success",
            color="green",
            variant="light",
            mt="lg",
        )

    return new_state, complete_message


# Intelligence extraction callback
@app.callback(
    [
        Output("app-store", "data", allow_duplicate=True),
        Output("intelligence-error", "children"),
        Output("intelligence-error", "style"),
    ],
    Input("extract-intelligence-btn", "n_clicks"),
    State("app-store", "data"),
    prevent_initial_call=True,
    running=[
        (Output("extract-intelligence-btn", "loading"), True, False),
    ],
)
def extract_intelligence_handler(n_clicks, store_data):
    """Extract intelligence from transcript."""
    import asyncio

    if not n_clicks:
        return dash.no_update, "", {"display": "none"}

    current_state = store_data or get_default_state()
    transcript_data = current_state.get("transcript_data", {})

    # Run extraction asynchronously
    result = asyncio.run(extract_intelligence(transcript_data, current_state))

    if not result.get("success"):
        error_msg = result.get("error", "Extraction failed")
        error_div = dmc.Alert(
            error_msg,
            title="Extraction Failed",
            color="red",
            variant="light",
        )
        # Update store with error
        new_state = current_state.copy()
        new_state.update({
            "intelligence_error": error_msg,
            "intelligence_running": False,
            "intelligence_status": "",
            "intelligence_progress": 0.0,
        })
        return (
            new_state,
            error_div,
            {"display": "block"},
        )

    # Update store
    new_state = current_state.copy()
    updates = {k: v for k, v in result.items() if k not in ("success", "error", "data")}
    new_state.update(updates)

    return new_state, "", {"display": "none"}


# Update intelligence content (prompt vs results) when intelligence data changes
@app.callback(
    Output("intelligence-content", "children"),
    Input("app-store", "data"),
)
def update_intelligence_content(store_data):
    """Update intelligence content to show prompt or results based on data availability."""
    from app.components.intelligence import extraction_prompt, intelligence_results

    data = store_data or get_default_state()
    if has_intelligence(data):
        return intelligence_results(data)
    else:
        return extraction_prompt(data)


# Update summary content when intelligence data changes
@app.callback(
    Output("summary-content", "children"),
    Input("app-store", "data"),
)
def update_summary_content(store_data):
    """Update summary content when intelligence data is available."""
    from dash import dcc

    data = store_data or get_default_state()
    summary_text = get_intelligence_summary_text(data)

    return dcc.Markdown(
        summary_text,
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
    # We don't need to import upload_steps here since we return a component

    data = store_data or get_default_state()
    has_file = bool(data.get("vtt_content", ""))

    if not has_file:
        return "", {"display": "none"}, upload_steps()

    file_name = data.get("uploaded_file_name", "")
    file_size = get_upload_size_display(data)
    preview = data.get("upload_preview", "")
    truncated = data.get("upload_preview_truncated", False)

    details = dmc.Card(
        withBorder=True,
        shadow="sm",
        padding="lg",
        radius="md",
        mt="lg",
        children=[
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Title("File Details", order=4),
                    dmc.Button(
                        "Remove",
                        id="clear-upload-btn",
                        variant="light",
                        color="red",
                        size="xs",
                        leftSection=dmc.Text("✕"),
                    ),
                ],
            ),
            dmc.SimpleGrid(
                cols=2,
                mt="md",
                children=[
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Text("Filename", size="xs", c="dimmed", tt="uppercase", fw=700),
                            dmc.Text(file_name, size="sm", fw=500),
                        ],
                    ),
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Text("Size", size="xs", c="dimmed", tt="uppercase", fw=700),
                            dmc.Text(file_size, size="sm", fw=500),
                        ],
                    ),
                ],
            ),
            dmc.Stack(
                gap="xs",
                mt="md",
                children=[
                    dmc.Text("Preview", size="xs", c="dimmed", tt="uppercase", fw=700),
                    dmc.Code(
                        preview,
                        block=True,
                        style={"maxHeight": "200px", "overflowY": "auto"},
                    ),
                    (
                        dmc.Text(
                            "Preview truncated to first 2000 characters.",
                            size="xs",
                            c="dimmed",
                            mt=5,
                        )
                        if truncated
                        else html.Div()
                    ),
                ],
            ),
        ],
    )

    return details, {"display": "block"}, html.Div()


# Download callbacks - split into separate callbacks to avoid validation issues
@app.callback(
    Output("download-data", "data", allow_duplicate=True),
    [
        Input("download-transcript-txt", "n_clicks"),
        Input("download-transcript-md", "n_clicks"),
        Input("download-transcript-vtt", "n_clicks"),
    ],
    State("app-store", "data"),
    prevent_initial_call=True,
)
def handle_transcript_download(txt_clicks, md_clicks, vtt_clicks, store_data):
    """Handle transcript file downloads."""
    from dash import callback_context

    if not callback_context.triggered:
        return None

    triggered = callback_context.triggered[0]
    button_id = triggered["prop_id"].split(".")[0]
    prop_value = triggered.get("value")

    # Only proceed if button was actually clicked (value must be > 0)
    if not button_id or prop_value is None or prop_value == 0:
        return None

    data = store_data or get_default_state()
    transcript_data = data.get("transcript_data", {})
    if not transcript_data:
        return None

    format_type = button_id.split("-")[-1]
    filename_base = data.get("uploaded_file_name", "transcript.vtt")
    filename = generate_download_filename(filename_base, "cleaned", format_type)

    try:
        content, mime_type = generate_export_content(transcript_data, format_type)
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        return {"content": str(content), "filename": filename, "type": mime_type}
    except Exception as e:
        import logging
        logging.exception("Download failed: %s", e)
        return None


@app.callback(
    Output("download-data", "data", allow_duplicate=True),
    [
        Input("download-intelligence-txt", "n_clicks"),
        Input("download-intelligence-md", "n_clicks"),
    ],
    State("app-store", "data"),
    prevent_initial_call=True,
)
def handle_intelligence_download(txt_clicks, md_clicks, store_data):
    """Handle intelligence file downloads."""
    from dash import callback_context

    if not callback_context.triggered:
        return None

    triggered = callback_context.triggered[0]
    button_id = triggered["prop_id"].split(".")[0]
    prop_value = triggered.get("value")

    # Only proceed if button was actually clicked (value must be > 0)
    if not button_id or prop_value is None or prop_value == 0:
        return None

    data = store_data or get_default_state()
    intelligence_data = data.get("intelligence_data", {})
    if not intelligence_data:
        return None

    format_type = button_id.split("-")[-1]
    filename_base = data.get("uploaded_file_name", "transcript.vtt")
    filename = generate_download_filename(filename_base, "intelligence", format_type)

    try:
        content, mime_type = generate_export_content(intelligence_data, format_type)
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        return {"content": str(content), "filename": filename, "type": mime_type}
    except Exception as e:
        import logging
        logging.exception("Download failed: %s", e)
        return None


if __name__ == "__main__":
    app.run(debug=True, port=8050)
