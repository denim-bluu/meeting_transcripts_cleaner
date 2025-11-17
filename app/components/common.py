"""Common reusable UI components."""

from dash import dcc, html


def missing_transcript_notice(message: str = ""):
    """Notice shown when no transcript is available.

    Args:
        message: Custom message (optional)
    """
    default_message = (
        "No processed transcript available. Upload and process a VTT file first."
    )
    return html.Div(
        [
            html.Span(
                "⚠️",
                style={
                    "fontSize": "1.25rem",
                    "color": "#000000",
                    "marginRight": "0.5rem",
                },
            ),
            html.Div(
                [
                    html.P(
                        message or default_message,
                        style={
                            "fontSize": "0.875rem",
                            "fontWeight": "700",
                            "color": "#000000",
                            "marginBottom": "0.75rem",
                        },
                    ),
                    dcc.Link(
                        "Go to Upload",
                        href="/",
                        style={
                            "display": "inline-flex",
                            "width": "fit-content",
                            "alignItems": "center",
                            "padding": "0.75rem 1.5rem",
                            "backgroundColor": "#000000",
                            "color": "#fbbf24",
                            "fontWeight": "700",
                            "border": "4px solid #fbbf24",
                            "textDecoration": "none",
                        },
                    ),
                ],
                style={"flex": "1", "display": "flex", "flexDirection": "column"},
            ),
        ],
        style={
            "marginTop": "1.5rem",
            "display": "flex",
            "alignItems": "flex-start",
            "gap": "0.75rem",
            "padding": "1rem",
            "backgroundColor": "#fef08a",
            "border": "4px solid #000000",
        },
    )


def export_button(
    label: str,
    icon: str,
    format_type: str,
    button_id: str,
    disabled: bool = False,
):
    """Generic export button component.

    Args:
        label: Button label (e.g., "TXT", "Markdown")
        icon: Icon emoji or name
        format_type: Format identifier (e.g., "txt", "md")
        button_id: Unique button ID for callback
        disabled: Whether button is disabled
    """
    return html.Button(
        f"{icon} Download {label}",
        id=button_id,
        n_clicks=0,
        disabled=disabled,
        style={
            "width": "100%",
            "display": "flex",
            "justifyContent": "center",
            "padding": "0.5rem 1rem",
            "backgroundColor": "#ffffff",
            "border": "4px solid #000000",
            "fontSize": "0.875rem",
            "fontWeight": "700",
            "color": "#000000",
            "cursor": "pointer" if not disabled else "not-allowed",
            "opacity": "0.4" if disabled else "1",
        },
    )


def export_section(
    title: str,
    description: str,
    formats: list[tuple[str, str, str]],
    button_ids: dict[str, str],
    disabled: bool = False,
    grid_cols: str = "repeat(3, 1fr)",
):
    """Generic export section component.

    Args:
        title: Section title
        description: Section description
        formats: List of (label, icon, format_type) tuples
        button_ids: Dict mapping format_type to button ID
        disabled: Whether buttons are disabled
        grid_cols: Grid column template
    """
    return html.Section(
        [
            html.H3(
                title,
                style={
                    "fontSize": "1.25rem",
                    "fontWeight": "900",
                    "color": "#000000",
                },
            ),
            html.P(
                description,
                style={
                    "marginTop": "0.25rem",
                    "fontSize": "0.875rem",
                    "fontWeight": "700",
                    "color": "#000000",
                },
            ),
            html.Div(
                [
                    export_button(
                        label=label,
                        icon=icon,
                        format_type=format_type,
                        button_id=button_ids[format_type],
                        disabled=disabled,
                    )
                    for label, icon, format_type in formats
                ],
                style={
                    "marginTop": "1rem",
                    "display": "grid",
                    "gridTemplateColumns": grid_cols,
                    "gap": "0.75rem",
                },
            ),
            html.Div(
                id=f"download-error-{title.lower().replace(' ', '-')}",
                style={"display": "none"},
            ),
        ],
        style={"display": "flex", "flexDirection": "column", "gap": "0.5rem"},
    )
