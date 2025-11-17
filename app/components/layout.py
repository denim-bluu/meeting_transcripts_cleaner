"""Layout primitives shared across pages."""

from dash import dcc, html


def header():
    """Application header with navigation."""
    return html.Header(
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            "📄",
                            style={"fontSize": "2rem", "marginRight": "0.75rem"},
                        ),
                        html.Div(
                            [
                                html.H1(
                                    "Meeting Transcript Tool",
                                    style={
                                        "fontSize": "1.25rem",
                                        "fontWeight": "700",
                                        "color": "#ffffff",
                                        "margin": 0,
                                    },
                                ),
                                html.P(
                                    "Clean transcripts, review quality, and extract meeting intelligence.",
                                    style={
                                        "fontSize": "0.875rem",
                                        "color": "#fef08a",
                                        "fontWeight": "500",
                                        "margin": 0,
                                    },
                                ),
                            ],
                            style={"marginLeft": "0.75rem"},
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center"},
                ),
                html.Nav(
                    [
                        nav_link("Upload", "/"),
                        nav_link("Review", "/review"),
                        nav_link("Intelligence", "/intelligence"),
                    ],
                    style={
                        "display": "flex",
                        "alignItems": "center",
                        "gap": "1.5rem",
                    },
                ),
            ],
            style={
                "maxWidth": "1200px",
                "margin": "0 auto",
                "padding": "0 1rem",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "space-between",
            },
        ),
        style={
            "backgroundColor": "#000000",
            "padding": "1rem 0",
            "borderBottom": "4px solid #fbbf24",
        },
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
            "border": "2px solid transparent",
        },
        className="nav-link",
    )


def page_container(*children):
    """Main page container with header."""
    return html.Main(
        [
            header(),
            html.Div(
                list(children),
                style={
                    "maxWidth": "1200px",
                    "margin": "0 auto",
                    "padding": "2.5rem 1rem",
                },
            ),
        ],
        style={
            "minHeight": "100vh",
            "backgroundColor": "#fefce8",
            "fontFamily": "'Montserrat', sans-serif",
        },
    )
