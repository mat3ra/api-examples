"""Domain-specific charts for property visualization in notebooks."""

import plotly.graph_objects as go
from pymatgen.analysis.phase_diagram import PDPlotter, PhaseDiagram

TEXT_SHADOW = "2px 2px 4px rgba(0,0,0,0.8), " "-2px -2px 4px rgba(0,0,0,0.8), " "0px 0px 8px rgba(0,0,0,0.9)"


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
        trace.marker.size = 20
        if trace.name == "Stable":
            trace.textposition = "top center"
            trace.textfont = dict(size=16, color="#FFFFFF", family="Arial Black", shadow=TEXT_SHADOW)
        else:
            trace.textposition = "bottom center"
            trace.textfont = dict(size=14, color="#FF6666", family="Arial Black", shadow=TEXT_SHADOW)

    fig.update_layout(
        height=900,
        width=1000,
        title=dict(text="Phase Diagram (Convex Hull)", font=dict(size=22, color="white")),
        margin=dict(l=80, r=80, t=80, b=80),
        paper_bgcolor="#1e1e1e",
        plot_bgcolor="#1e1e1e",
        ternary=dict(
            bgcolor="#1e1e1e",
            aaxis=dict(
                title=dict(font=dict(size=22, color="white")),
                linecolor="#555",
                gridcolor="#333",
                tickfont=dict(color="#aaa"),
            ),
            baxis=dict(
                title=dict(font=dict(size=22, color="white")),
                linecolor="#555",
                gridcolor="#333",
                tickfont=dict(color="#aaa"),
            ),
            caxis=dict(
                title=dict(font=dict(size=22, color="white")),
                linecolor="#555",
                gridcolor="#333",
                tickfont=dict(color="#aaa"),
            ),
        ),
        legend=dict(font=dict(size=14, color="white")),
    )

    return fig
