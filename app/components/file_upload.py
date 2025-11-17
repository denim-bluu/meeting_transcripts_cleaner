"""Upload and processing components."""

from dash import dcc, html


def upload_dropzone():
    """File upload dropzone."""
    return dcc.Upload(
        html.Div(
            html.Div(
                [
                    html.Div("☁️", style={"fontSize": "3rem", "marginBottom": "1rem"}),
                    html.H3(
                        "Upload VTT File",
                        style={
                            "marginTop": "1rem",
                            "fontSize": "1.125rem",
                            "fontWeight": "700",
                            "color": "#000000",
                        },
                    ),
                    html.P(
                        "Drag and drop or click to upload your meeting transcript.",
                        style={
                            "marginTop": "0.25rem",
                            "fontSize": "0.875rem",
                            "fontWeight": "500",
                            "color": "#000000",
                        },
                    ),
                    html.Span(
                        "VTT files only",
                        style={
                            "marginTop": "0.5rem",
                            "fontSize": "0.75rem",
                            "fontWeight": "700",
                            "color": "#000000",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "flexDirection": "column",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "padding": "2rem",
                },
            ),
            style={
                "width": "100%",
                "border": "4px dashed #000000",
                "cursor": "pointer",
                "backgroundColor": "#fef08a",
            },
        ),
        id="upload-data",
        accept=".vtt",
        multiple=False,
        style={"width": "100%"},
    )


def upload_error_banner():
    """Error banner for upload issues."""
    return html.Div(
        id="upload-error",
        children="",
        style={"display": "none"},
    )


def upload_details():
    """Display uploaded file details."""
    return html.Div(
        id="upload-details",
        style={"display": "none"},
    )


def upload_steps():
    """Information about processing steps."""
    return html.Div(
        [
            html.H3(
                "What happens during processing",
                style={
                    "fontSize": "1rem",
                    "fontWeight": "700",
                    "color": "#000000",
                },
            ),
            html.Ul(
                [
                    html.Li(
                        "📤 Upload: File loaded into the app",
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                    html.Li(
                        "🔧 Parse: VTT parsed and chunked for AI processing",
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                    html.Li(
                        "🤖 Clean: AI agents clean speech-to-text errors",
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                    html.Li(
                        "📊 Review: Quality review ensures accuracy",
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                    html.Li(
                        "✅ Complete: Cleaned transcript ready for review",
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                ],
                style={
                    "marginTop": "0.75rem",
                    "listStyle": "disc",
                    "paddingLeft": "1.5rem",
                },
            ),
        ],
        style={
            "marginTop": "1.5rem",
            "padding": "1rem",
            "backgroundColor": "#cffafe",
            "border": "4px dashed #000000",
        },
    )


def processing_progress_panel():
    """Processing progress indicator."""
    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        "Processing Status",
                        style={
                            "fontSize": "0.75rem",
                            "textTransform": "uppercase",
                            "fontWeight": "700",
                            "color": "#000000",
                        },
                    ),
                    html.P(
                        id="processing-status",
                        style={"fontSize": "0.875rem", "fontWeight": "700", "color": "#000000"},
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                },
            ),
            html.Div(
                html.Div(
                    html.Div(
                        id="processing-progress-bar",
                        style={
                            "width": "0%",
                            "backgroundColor": "#000000",
                            "height": "100%",
                            "transition": "width 0.3s ease",
                        },
                    ),
                    id="processing-progress",
                    style={
                        "width": "100%",
                        "backgroundColor": "#fbbf24",
                        "height": "0.75rem",
                        "borderRadius": "0px",
                        "overflow": "hidden",
                    },
                ),
                style={"marginTop": "0.75rem"},
            ),
            html.Div(
                id="transcript-error",
                style={"display": "none"},
            ),
        ],
        style={
            "marginTop": "1.5rem",
            "padding": "1rem",
            "backgroundColor": "#ffffff",
            "border": "4px solid #000000",
        },
    )


def process_action_buttons():
    """Action buttons for processing."""
    return html.Div(
        html.Button(
            "Process VTT File",
            id="process-btn",
            n_clicks=0,
            style={
                "width": "100%",
                "display": "flex",
                "justifyContent": "center",
                "padding": "0.75rem 1.5rem",
                "backgroundColor": "#000000",
                "color": "#fbbf24",
                "fontWeight": "700",
                "border": "4px solid #fbbf24",
                "cursor": "pointer",
            },
        ),
        style={"marginTop": "1.5rem"},
    )


def upload_panel():
    """Main upload panel component."""
    return html.Div(
        [
            upload_dropzone(),
            upload_error_banner(),
            upload_details(),
            process_action_buttons(),
            processing_progress_panel(),
            html.Div(id="upload-steps-container"),
        ],
        style={"width": "100%", "maxWidth": "48rem", "margin": "0 auto"},
    )
