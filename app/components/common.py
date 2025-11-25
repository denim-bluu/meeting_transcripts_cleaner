"""Common reusable UI components using Dash Mantine Components."""

from dash import dcc, html
import dash_mantine_components as dmc


def missing_transcript_notice(message: str = ""):
    """Notice shown when no transcript is available."""
    default_message = (
        "No processed transcript available. Upload and process a VTT file first."
    )
    return dmc.Alert(
        title="Missing Transcript",
        children=[
            dmc.Text(message or default_message),
            dmc.Anchor(
                "Go to Upload",
                href="/",
                underline=False,
                fw=700,
                c="blue",
                mt="sm",
                style={"display": "inline-block"},
            ),
        ],
        color="yellow",
        variant="light",
        withCloseButton=False,
        icon=dmc.Text("⚠️", size="lg"),
        mt="lg",
    )


def export_button(
    label: str,
    icon: str,
    format_type: str,
    button_id: str,
    disabled: bool = False,
):
    """Generic export button component."""
    return dmc.Button(
        f"Download {label}",
        id=button_id,
        leftSection=icon,
        disabled=disabled,
        variant="outline",
        fullWidth=True,
        color="dark",
    )


def export_section(
    title: str,
    description: str,
    formats: list[tuple[str, str, str]],
    button_ids: dict[str, str],
    disabled: bool = False,
    grid_cols: int = 3,
):
    """Generic export section component."""
    return dmc.Stack(
        gap="xs",
        children=[
            dmc.Title(title, order=3),
            dmc.Text(description, size="sm", c="dimmed"),
            dmc.SimpleGrid(
                cols=grid_cols,
                spacing="sm",
                mt="sm",
                children=[
                    export_button(
                        label=label,
                        icon=icon,
                        format_type=format_type,
                        button_id=button_ids[format_type],
                        disabled=disabled,
                    )
                    for label, icon, format_type in formats
                ],
            ),
            html.Div(
                id=f"download-error-{title.lower().replace(' ', '-')}",
                style={"display": "none"},
            ),
        ],
        mt="xl",
    )
