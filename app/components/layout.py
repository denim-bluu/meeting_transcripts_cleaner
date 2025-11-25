"""Layout primitives shared across pages using Dash Mantine Components."""

from dash import dcc, html
import dash_mantine_components as dmc


def header():
    """Application header with navigation."""
    return dmc.Paper(
        p="md",
        radius=0,
        bg="black",
        style={"borderBottom": "4px solid #fbbf24"},
        children=[
            dmc.Container(
                size="xl",
                children=[
                    dmc.Group(
                        justify="space-between",
                        children=[
                            dmc.Group(
                                gap="xs",
                                children=[
                                    dmc.Text("📄", size="xl"),
                                    dmc.Stack(
                                        gap=0,
                                        children=[
                                            dmc.Title(
                                                "Meeting Transcript Tool",
                                                order=1,
                                                c="white",
                                                size="h4",
                                            ),
                                            dmc.Text(
                                                "Clean transcripts, review quality, and extract meeting intelligence.",
                                                c="yellow.1",
                                                size="sm",
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Group(
                                gap="lg",
                                children=[
                                    nav_link("Upload", "/"),
                                    nav_link("Review", "/review"),
                                    nav_link("Intelligence", "/intelligence"),
                                ],
                            ),
                        ],
                    )
                ],
            )
        ],
    )


def nav_link(label: str, href: str):
    """Navigation link component."""
    return dcc.Link(
        label,
        href=href,
        style={
            "fontSize": "0.875rem",
            "fontWeight": "700",
            "color": "#ffffff",
            "textDecoration": "none",
            "padding": "0.25rem 0.75rem",
        },
    )


def page_container(*children):
    """Main page container with header."""
    return html.Main(
        [
            header(),
            dmc.Container(
                size="xl",
                py="xl",
                children=list(children),
            ),
        ],
        style={
            "minHeight": "100vh",
            "backgroundColor": "#fefce8",
            "fontFamily": "'Montserrat', sans-serif",
        },
    )
