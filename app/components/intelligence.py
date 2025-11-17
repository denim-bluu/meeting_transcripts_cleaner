"""Intelligence extraction workspace."""

from __future__ import annotations

from dash import dcc, html

from app.components.common import (
    export_section as common_export_section,
    missing_transcript_notice,
)
from app.components.metrics import metric_card
from app.state import (
    ActionItemDisplay,
    KeyAreaDisplay,
    ValidationDisplay,
    get_has_transcript,
    get_has_intelligence,
    get_intelligence_confidence_display,
    get_intelligence_key_area_count,
    get_intelligence_action_item_count,
    get_intelligence_has_key_areas,
    get_intelligence_key_area_cards,
    get_intelligence_has_action_items,
    get_intelligence_action_item_cards,
    get_intelligence_validation_display,
    get_cleansed_transcript_text,
    get_intelligence_summary_text,
)


def intelligence_workspace():
    """Main intelligence workspace."""
    if not get_has_transcript():
        return html.Section(
            [
                html.H2(
                    "Meeting Intelligence",
                    style={
                        "fontSize": "1.875rem",
                        "fontWeight": "900",
                        "color": "#000000",
                    },
                ),
                html.P(
                    "Generate executive summaries, key themes, and action items from the cleaned transcript.",
                    style={
                        "marginTop": "0.5rem",
                        "fontSize": "0.875rem",
                        "fontWeight": "700",
                        "color": "#000000",
                    },
                ),
                missing_transcript_notice(
                    "No processed transcript available. Upload and process a VTT file to enable intelligence extraction."
                ),
            ],
            style={"maxWidth": "72rem", "margin": "0 auto"},
        )

    return html.Section(
        [
            html.H2(
                "Meeting Intelligence",
                style={
                    "fontSize": "1.875rem",
                    "fontWeight": "900",
                    "color": "#000000",
                },
            ),
            html.P(
                "Generate executive summaries, key themes, and action items from the cleaned transcript.",
                style={
                    "marginTop": "0.5rem",
                    "fontSize": "0.875rem",
                    "fontWeight": "700",
                    "color": "#000000",
                },
            ),
            html.Div(
                [
                    dcc.Interval(id="intelligence-interval", interval=500, n_intervals=0),
                    # Hidden components for callbacks
                    html.Div(id="intelligence-status", style={"display": "none"}),
                    html.Div(id="intelligence-progress", style={"display": "none"}),
                    html.Div(id="intelligence-error", style={"display": "none"}),
                    html.Div(id="intelligence-status-display", style={"display": "none"}),
                    cleansed_transcript_section(),
                    extraction_prompt() if not get_has_intelligence() else intelligence_results(),
                ],
                style={"display": "flex", "flexDirection": "column", "gap": "2rem"},
            ),
        ],
        style={"maxWidth": "72rem", "margin": "0 auto"},
    )


def extraction_prompt():
    """Prompt to extract intelligence."""
    return html.Section(
        [
            html.Div(
                [
                    html.Span("🧠", style={"fontSize": "1.5rem", "marginRight": "0.75rem"}),
                    html.Div(
                        [
                            html.H3(
                                "Extract Meeting Intelligence",
                                style={
                                    "fontSize": "1.125rem",
                                    "fontWeight": "700",
                                    "color": "#000000",
                                },
                            ),
                            html.P(
                                "Run the intelligence pipeline to generate summaries, key areas, and action items.",
                                style={
                                    "marginTop": "0.25rem",
                                    "fontSize": "0.875rem",
                                    "fontWeight": "500",
                                    "color": "#000000",
                                },
                            ),
                        ]
                    ),
                ],
                style={"display": "flex", "alignItems": "flex-start", "gap": "0.75rem"},
            ),
            html.Ul(
                [
                    html.Li(
                        "📋 Executive summaries",
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                    html.Li(
                        "🎯 Action items with owners and due dates",
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                    html.Li(
                        "🧩 Key themes with supporting evidence",
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                    html.Li(
                        "✅ Validation notes and unresolved topics",
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                ],
                style={
                    "marginTop": "1rem",
                    "listStyle": "disc",
                    "paddingLeft": "1.5rem",
                },
            ),
            # Progress display container - shows extraction progress
            html.Div(
                extraction_progress_panel(),
                id="intelligence-progress-display-container",
                style={"display": "none"},
            ),
            html.Button(
                "🧠 Extract Intelligence",
                id="extract-intelligence-btn",
                n_clicks=0,
                style={
                    "marginTop": "1.25rem",
                    "display": "inline-flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "padding": "0.75rem 1.5rem",
                    "backgroundColor": "#000000",
                    "color": "#fbbf24",
                    "fontWeight": "700",
                    "border": "4px solid #fbbf24",
                    "cursor": "pointer",
                },
            ),
            # intelligence-error is in main layout
        ],
        style={
            "marginTop": "1.5rem",
            "padding": "1.5rem",
            "backgroundColor": "#ffffff",
            "border": "4px solid #000000",
            "display": "flex",
            "flexDirection": "column",
            "gap": "1rem",
        },
    )


def extraction_progress_panel():
    """Progress panel for intelligence extraction."""
    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        "Extraction Status",
                        style={
                            "fontSize": "0.75rem",
                            "textTransform": "uppercase",
                            "fontWeight": "700",
                            "color": "#000000",
                        },
                    ),
                    html.Div(
                        [
                            html.Span("⏳", style={"marginRight": "0.5rem"}),
                            html.P(
                                id="intelligence-status-display-inner",
                                style={
                                    "fontSize": "0.875rem",
                                    "fontWeight": "700",
                                    "color": "#000000",
                                },
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center"},
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
                        id="intelligence-progress-bar-inner",
                        style={
                            "width": "0%",
                            "backgroundColor": "#6366f1",
                            "height": "100%",
                            "transition": "width 0.3s ease",
                        },
                    ),
                    id="intelligence-progress-inner",
                    style={
                        "width": "100%",
                        "backgroundColor": "#e5e7eb",
                        "height": "0.75rem",
                        "borderRadius": "999px",
                        "overflow": "hidden",
                    },
                ),
                style={"marginTop": "0.75rem"},
            ),
        ],
        style={
            "marginTop": "1.25rem",
            "padding": "1rem",
            "border": "4px solid #000000",
            "backgroundColor": "#fef08a",
        },
    )


def intelligence_results():
    """Intelligence results display."""
    return html.Div(
        [
            intelligence_metrics_header(),
            summary_section(),
            key_areas_section(),
            action_items_section(),
            validation_section(),
            export_section(),
        ],
        style={"display": "flex", "flexDirection": "column", "gap": "2rem"},
    )


def intelligence_metrics_header():
    """Metrics header for intelligence."""
    return html.Section(
        [
            html.H3(
                "Pipeline Overview",
                style={
                    "fontSize": "1.25rem",
                    "fontWeight": "900",
                    "color": "#000000",
                },
            ),
            html.Div(
                [
                    metric_card("Confidence", get_intelligence_confidence_display()),
                    metric_card("Key Areas", get_intelligence_key_area_count()),
                    metric_card("Action Items", get_intelligence_action_item_count()),
                ],
                style={
                    "marginTop": "1rem",
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(200px, 1fr))",
                    "gap": "1rem",
                },
            ),
        ],
        style={"display": "flex", "flexDirection": "column", "gap": "0.5rem"},
    )


def cleansed_transcript_section():
    """Section showing cleansed transcript."""
    text = get_cleansed_transcript_text()
    return html.Section(
        [
            html.H3(
                "Cleansed Transcript",
                style={
                    "fontSize": "1.25rem",
                    "fontWeight": "900",
                    "color": "#000000",
                },
            ),
            html.P(
                "Review the cleaned transcript that will be used for intelligence extraction.",
                style={
                    "marginTop": "0.25rem",
                    "fontSize": "0.875rem",
                    "fontWeight": "700",
                    "color": "#000000",
                },
            ),
            html.Div(
                html.Pre(
                    text,
                    style={
                        "marginTop": "0.5rem",
                        "whiteSpace": "pre-wrap",
                        "fontSize": "0.875rem",
                        "lineHeight": "1.75",
                        "backgroundColor": "#ffffff",
                        "border": "4px solid #000000",
                        "padding": "1rem",
                        "maxHeight": "24rem",
                        "overflowY": "auto",
                        "fontFamily": "monospace",
                    },
                )
                if text
                else html.Div(
                    "No cleansed transcript available.",
                    style={
                        "marginTop": "0.5rem",
                        "padding": "1rem",
                        "fontSize": "0.875rem",
                        "fontWeight": "700",
                        "color": "#000000",
                        "backgroundColor": "#cffafe",
                        "border": "4px solid #000000",
                    },
                ),
                style={"marginTop": "0.5rem"},
            ),
        ],
        style={"display": "flex", "flexDirection": "column", "gap": "0.5rem"},
    )


def summary_section():
    """Executive summary section."""
    return html.Section(
        [
            html.Div(
                [
                    html.H3(
                        "Executive Summary",
                        style={
                            "fontSize": "1.25rem",
                            "fontWeight": "900",
                            "color": "#000000",
                        },
                    ),
                    html.Button(
                        "🔄 Regenerate Summary",
                        id="regenerate-summary-btn",
                        n_clicks=0,
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "padding": "0.5rem 1rem",
                            "fontSize": "0.875rem",
                            "fontWeight": "700",
                            "color": "#000000",
                            "backgroundColor": "#ffffff",
                            "border": "4px solid #000000",
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
                id="summary-content",
                children=html.Div(
                    get_intelligence_summary_text(),
                    style={
                        "marginTop": "0.5rem",
                        "padding": "1rem",
                        "backgroundColor": "#ffffff",
                        "border": "4px solid #000000",
                    },
                ),
            ),
        ],
        style={"display": "flex", "flexDirection": "column", "gap": "0.5rem"},
    )


def key_areas_section():
    """Key areas and themes section."""
    if not get_intelligence_has_key_areas():
        return html.Section(
            [
                html.Div(
                    [
                        html.H3(
                            "Key Areas & Themes",
                            style={
                                "fontSize": "1.25rem",
                                "fontWeight": "900",
                                "color": "#000000",
                            },
                        ),
                        html.P(
                            "Explore thematic clusters with supporting evidence and follow-up actions.",
                            style={
                                "marginTop": "0.25rem",
                                "fontSize": "0.875rem",
                                "fontWeight": "700",
                                "color": "#000000",
                            },
                        ),
                    ]
                ),
                html.Div(
                    "No key areas were generated for this meeting.",
                    style={
                        "marginTop": "1rem",
                        "fontSize": "0.875rem",
                        "fontWeight": "700",
                        "color": "#000000",
                    },
                ),
            ],
            style={"display": "flex", "flexDirection": "column", "gap": "0.5rem"},
        )

    areas = get_intelligence_key_area_cards()
    area_cards = [key_area_card(area) for area in areas]

    return html.Section(
        [
            html.Div(
                [
                    html.H3(
                        "Key Areas & Themes",
                        style={
                            "fontSize": "1.25rem",
                            "fontWeight": "900",
                            "color": "#000000",
                        },
                    ),
                    html.P(
                        "Explore thematic clusters with supporting evidence and follow-up actions.",
                        style={
                            "marginTop": "0.25rem",
                            "fontSize": "0.875rem",
                            "fontWeight": "700",
                            "color": "#000000",
                        },
                    ),
                ]
            ),
            html.Div(
                area_cards,
                style={"marginTop": "1rem", "display": "flex", "flexDirection": "column", "gap": "1rem"},
            ),
        ],
        style={"display": "flex", "flexDirection": "column", "gap": "0.5rem"},
    )


def key_area_card(area: KeyAreaDisplay):
    """Individual key area card."""
    highlights_section = (
        html.Div(
            [
                html.Span(
                    "Highlights",
                    style={
                        "fontSize": "0.75rem",
                        "fontWeight": "700",
                        "color": "#000000",
                        "textTransform": "uppercase",
                    },
                ),
                html.Ul(
                    [
                        html.Li(
                            highlight,
                            style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                        )
                        for highlight in area.get("highlights", [])
                    ],
                    style={
                        "marginTop": "0.5rem",
                        "listStyle": "disc",
                        "paddingLeft": "1.5rem",
                    },
                ),
            ],
            style={"marginTop": "1rem"},
        )
        if area.get("has_highlights", False)
        else html.Div()
    )

    decisions_section = (
        html.Div(
            [
                html.Span(
                    "Decisions",
                    style={
                        "fontSize": "0.75rem",
                        "fontWeight": "700",
                        "color": "#000000",
                        "textTransform": "uppercase",
                    },
                ),
                html.Ul(
                    [
                        html.Li(
                            decision,
                            style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                        )
                        for decision in area.get("decisions", [])
                    ],
                    style={
                        "marginTop": "0.5rem",
                        "listStyle": "disc",
                        "paddingLeft": "1.5rem",
                    },
                ),
            ],
            style={"marginTop": "1rem"},
        )
        if area.get("has_decisions", False)
        else html.Div()
    )

    actions_section = (
        html.Div(
            [
                html.Span(
                    "Actions",
                    style={
                        "fontSize": "0.75rem",
                        "fontWeight": "700",
                        "color": "#000000",
                        "textTransform": "uppercase",
                    },
                ),
                html.Ul(
                    [
                        html.Li(
                            action,
                            style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                        )
                        for action in area.get("actions", [])
                    ],
                    style={
                        "marginTop": "0.5rem",
                        "listStyle": "disc",
                        "paddingLeft": "1.5rem",
                    },
                ),
            ],
            style={"marginTop": "1rem"},
        )
        if area.get("has_actions", False)
        else html.Div()
    )

    supporting_section = (
        html.Span(
            area["supporting_text"],
            style={
                "marginTop": "0.75rem",
                "fontSize": "0.75rem",
                "fontWeight": "700",
                "color": "#000000",
            },
        )
        if area.get("has_supporting", False)
        else html.Div()
    )

    return html.Div(
        [
            html.Div(
                [
                    html.H4(
                        area["title"],
                        style={
                            "fontSize": "1rem",
                            "fontWeight": "900",
                            "color": "#000000",
                        },
                    ),
                    html.Span(
                        area["meta"],
                        style={
                            "fontSize": "0.75rem",
                            "fontWeight": "700",
                            "color": "#000000",
                        },
                    ),
                ],
                style={"display": "flex", "flexDirection": "column"},
            ),
            html.P(
                area["summary"],
                style={
                    "marginTop": "0.75rem",
                    "fontSize": "0.875rem",
                    "fontWeight": "500",
                    "color": "#000000",
                },
            ),
            highlights_section,
            decisions_section,
            actions_section,
            supporting_section,
        ],
        style={
            "padding": "1.25rem",
            "backgroundColor": "#ffffff",
            "border": "4px solid #000000",
        },
    )


def action_items_section():
    """Action items section."""
    if not get_intelligence_has_action_items():
        return html.Section(
            [
                html.Div(
                    [
                        html.H3(
                            "Action Items",
                            style={
                                "fontSize": "1.25rem",
                                "fontWeight": "900",
                                "color": "#000000",
                            },
                        ),
                        html.P(
                            "Track owners, due dates, and confidence for each follow-up item.",
                            style={
                                "marginTop": "0.25rem",
                                "fontSize": "0.875rem",
                                "fontWeight": "700",
                                "color": "#000000",
                            },
                        ),
                    ]
                ),
                html.Div(
                    "No action items were generated for this meeting.",
                    style={
                        "marginTop": "1rem",
                        "fontSize": "0.875rem",
                        "fontWeight": "700",
                        "color": "#000000",
                    },
                ),
            ],
            style={"display": "flex", "flexDirection": "column", "gap": "0.5rem"},
        )

    items = get_intelligence_action_item_cards()
    item_cards = [action_item_card(item) for item in items]

    return html.Section(
        [
            html.Div(
                [
                    html.H3(
                        "Action Items",
                        style={
                            "fontSize": "1.25rem",
                            "fontWeight": "900",
                            "color": "#000000",
                        },
                    ),
                    html.P(
                        "Track owners, due dates, and confidence for each follow-up item.",
                        style={
                            "marginTop": "0.25rem",
                            "fontSize": "0.875rem",
                            "fontWeight": "700",
                            "color": "#000000",
                        },
                    ),
                ]
            ),
            html.Div(
                item_cards,
                style={
                    "marginTop": "1rem",
                    "display": "grid",
                    "gridTemplateColumns": "repeat(2, 1fr)",
                    "gap": "1rem",
                },
            ),
        ],
        style={"display": "flex", "flexDirection": "column", "gap": "0.5rem"},
    )


def action_item_card(item: ActionItemDisplay):
    """Individual action item card."""
    confidence_section = (
        html.Span(
            item["confidence_text"],
            style={
                "marginTop": "0.75rem",
                "fontSize": "0.75rem",
                "fontWeight": "700",
                "color": "#000000",
            },
        )
        if item.get("has_confidence", False)
        else html.Div()
    )

    return html.Div(
        [
            html.H4(
                item["title"],
                style={
                    "fontSize": "1rem",
                    "fontWeight": "900",
                    "color": "#000000",
                },
            ),
            html.Div(
                [
                    html.Span(
                        item["owner_text"],
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                    html.Span(
                        item["due_text"],
                        style={"fontSize": "0.875rem", "fontWeight": "500", "color": "#000000"},
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "space-between",
                    "marginTop": "0.5rem",
                },
            ),
            confidence_section,
        ],
        style={
            "padding": "1rem",
            "backgroundColor": "#ffffff",
            "border": "4px solid #000000",
        },
    )


def validation_section():
    """Validation and quality section."""
    details: ValidationDisplay = get_intelligence_validation_display()

    return html.Section(
        [
            html.H3(
                "Validation & Quality",
                style={
                    "fontSize": "1.25rem",
                    "fontWeight": "900",
                    "color": "#000000",
                },
            ),
            html.Div(
                html.Span(
                    details["status_label"],
                    className=details["status_class"],
                    style={
                        "fontSize": "0.875rem",
                        "fontWeight": "700",
                        "padding": "0.25rem 0.75rem",
                        "border": "4px solid #000000",
                    },
                ),
                style={"display": "inline-flex"},
            ),
            html.Div(
                [
                    html.Span(
                        "Detected Issues",
                        style={
                            "fontSize": "0.75rem",
                            "fontWeight": "700",
                            "color": "#000000",
                            "textTransform": "uppercase",
                        },
                    ),
                    html.Pre(
                        details["issues_text"],
                        style={
                            "marginTop": "0.5rem",
                            "whiteSpace": "pre-wrap",
                            "fontSize": "0.875rem",
                            "fontWeight": "500",
                            "color": "#000000",
                            "backgroundColor": "#ffffff",
                            "border": "4px solid #000000",
                            "padding": "0.5rem",
                        },
                    ),
                ],
                style={"marginTop": "1rem"},
            )
            if details.get("has_issues", False)
            else html.Div(),
            html.Div(
                [
                    html.Span(
                        "Unresolved Topics",
                        style={
                            "fontSize": "0.75rem",
                            "fontWeight": "700",
                            "color": "#000000",
                            "textTransform": "uppercase",
                        },
                    ),
                    html.Pre(
                        details["unresolved_text"],
                        style={
                            "marginTop": "0.5rem",
                            "whiteSpace": "pre-wrap",
                            "fontSize": "0.875rem",
                            "fontWeight": "500",
                            "color": "#000000",
                            "backgroundColor": "#ffffff",
                            "border": "4px solid #000000",
                            "padding": "0.5rem",
                        },
                    ),
                ],
                style={"marginTop": "1rem"},
            )
            if details.get("has_unresolved", False)
            else html.Div(),
            html.Div(
                [
                    html.Span(
                        "Validation Notes",
                        style={
                            "fontSize": "0.75rem",
                            "fontWeight": "700",
                            "color": "#000000",
                            "textTransform": "uppercase",
                        },
                    ),
                    html.Pre(
                        details["notes_text"],
                        style={
                            "marginTop": "0.5rem",
                            "whiteSpace": "pre-wrap",
                            "fontSize": "0.875rem",
                            "fontWeight": "500",
                            "color": "#000000",
                            "backgroundColor": "#ffffff",
                            "border": "4px solid #000000",
                            "padding": "0.5rem",
                        },
                    ),
                ],
                style={"marginTop": "1rem"},
            )
            if details.get("has_notes", False)
            else html.Div(),
        ],
        style={"display": "flex", "flexDirection": "column", "gap": "0.75rem"},
    )


def export_section():
    """Export section for intelligence data."""
    return common_export_section(
        title="Export Intelligence",
        description="Download the intelligence package as Markdown or plain text.",
        formats=[
            ("TXT", "📄", "txt"),
            ("Markdown", "📝", "md"),
        ],
        button_ids={
            "txt": "download-intelligence-txt",
            "md": "download-intelligence-md",
        },
        disabled=not get_has_intelligence(),
        grid_cols="repeat(2, 1fr)",
    )
