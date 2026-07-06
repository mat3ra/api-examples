"""Domain-specific charts for property visualization in notebooks."""

import plotly.graph_objects as go
from pymatgen.analysis.phase_diagram import PDPlotter, PhaseDiagram

# Layout
FIGURE_HEIGHT = 900
FIGURE_WIDTH = 1000
FIGURE_MARGIN = 80
FIGURE_TITLE = "Phase Diagram (Convex Hull)"

# Colors (dark theme)
BACKGROUND_COLOR = "#1e1e1e"
TEXT_COLOR_PRIMARY = "#FFFFFF"
TEXT_COLOR_UNSTABLE = "#FF6666"
TEXT_COLOR_SECONDARY = "#aaa"
LINE_COLOR = "#555"
GRID_COLOR = "#333"

# Typography
FONT_FAMILY = "Arial Black"
FONT_SIZE_TITLE = 22
FONT_SIZE_LABEL_STABLE = 16
FONT_SIZE_LABEL_UNSTABLE = 14
FONT_SIZE_LEGEND = 14
TEXT_SHADOW = "2px 2px 4px rgba(0,0,0,0.8), " "-2px -2px 4px rgba(0,0,0,0.8), " "0px 0px 8px rgba(0,0,0,0.9)"

# Markers
MARKER_SIZE = 20


def plot_convex_hull(phase_diagram: PhaseDiagram, show_unstable: float = 0.2) -> go.Figure:
    """Plot an interactive phase diagram with clean, readable labels.

    Uses plotly via pymatgen's PDPlotter. Labels show formula + energy as text,
    full info (including material ID) on hover. Uses an explicit dark background
    so the plot looks consistent in both light and dark IDE themes.

    Args:
        phase_diagram: pymatgen PhaseDiagram object.
        show_unstable: Energy threshold (eV/atom) for showing unstable entries.

    Returns:
        plotly Figure object.
    """
    fig = PDPlotter(phase_diagram, show_unstable=show_unstable).get_plot()

    for trace in fig.data:
        if not trace.hovertext:
            continue
        labels = []
        for hover_text in trace.hovertext:
            parts = hover_text.split("<br>")
            formula = parts[0].split("(")[0].strip()
            energy_status = parts[1].strip() if len(parts) > 1 else ""
            labels.append(f"<b>{formula}</b><br>{energy_status}")
        trace.text = tuple(labels)
        trace.mode = "markers+text"
        trace.marker.size = MARKER_SIZE
        if trace.name == "Stable":
            trace.textposition = "top center"
            trace.textfont = dict(
                size=FONT_SIZE_LABEL_STABLE, color=TEXT_COLOR_PRIMARY, family=FONT_FAMILY, shadow=TEXT_SHADOW
            )
        else:
            trace.textposition = "bottom center"
            trace.textfont = dict(
                size=FONT_SIZE_LABEL_UNSTABLE, color=TEXT_COLOR_UNSTABLE, family=FONT_FAMILY, shadow=TEXT_SHADOW
            )

    axis_style = dict(
        title=dict(font=dict(size=FONT_SIZE_TITLE, color=TEXT_COLOR_PRIMARY)),
        linecolor=LINE_COLOR,
        gridcolor=GRID_COLOR,
        tickfont=dict(color=TEXT_COLOR_SECONDARY),
    )

    fig.update_layout(
        height=FIGURE_HEIGHT,
        width=FIGURE_WIDTH,
        title=dict(text=FIGURE_TITLE, font=dict(size=FONT_SIZE_TITLE, color=TEXT_COLOR_PRIMARY)),
        margin=dict(l=FIGURE_MARGIN, r=FIGURE_MARGIN, t=FIGURE_MARGIN, b=FIGURE_MARGIN),
        paper_bgcolor=BACKGROUND_COLOR,
        plot_bgcolor=BACKGROUND_COLOR,
        ternary=dict(bgcolor=BACKGROUND_COLOR, aaxis=axis_style, baxis=axis_style, caxis=axis_style),
        legend=dict(font=dict(size=FONT_SIZE_LEGEND, color=TEXT_COLOR_PRIMARY)),
    )

    return fig
