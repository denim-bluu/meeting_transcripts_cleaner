"""Upload and processing components using Dash Mantine Components."""

from dash import dcc, html
import dash_mantine_components as dmc


def upload_dropzone():
    """File upload dropzone."""
    return dcc.Upload(
        id="upload-data",
        accept=".vtt",
        multiple=False,
        children=dmc.Paper(
            p="xl",
            radius="md",
            withBorder=True,
            style={
                "border": "4px dashed #e5e7eb",
                "backgroundColor": "#f9fafb",
                "cursor": "pointer",
            },
            children=[
                dmc.Stack(
                    align="center",
                    gap="xs",
                    children=[
                        dmc.Text("☁️", size="3rem"),
                        dmc.Text("Upload VTT File", size="lg", fw=700),
                        dmc.Text(
                            "Drag and drop or click to upload your meeting transcript.",
                            size="sm",
                            c="dimmed",
                        ),
                        dmc.Badge("VTT files only", color="gray", variant="light"),
                    ],
                )
            ],
        ),
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
    return dmc.Alert(
        title="What happens during processing",
        color="cyan",
        variant="light",
        children=[
            dmc.List(
                size="sm",
                spacing="xs",
                children=[
                    dmc.ListItem("📤 Upload: File loaded into the app"),
                    dmc.ListItem("🔧 Parse: VTT parsed and chunked for AI processing"),
                    dmc.ListItem("🤖 Clean: AI agents clean speech-to-text errors"),
                    dmc.ListItem("📊 Review: Quality review ensures accuracy"),
                    dmc.ListItem("✅ Complete: Cleaned transcript ready for review"),
                ],
            )
        ],
        mt="lg",
    )


def process_action_buttons():
    """Action buttons for processing."""
    return dmc.Button(
        "Process VTT File",
        id="process-btn",
        size="lg",
        fullWidth=True,
        color="dark",
        mt="lg",
        loading=False,
        disabled=False,
    )


def upload_panel():
    """Main upload panel component."""
    return dmc.Container(
        size="sm",
        children=[
            upload_dropzone(),
            upload_error_banner(),
            upload_details(),
            process_action_buttons(),
            html.Div(id="upload-steps-container"),
        ],
    )
