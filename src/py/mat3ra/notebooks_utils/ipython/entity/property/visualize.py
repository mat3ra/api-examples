import json
import time

from IPython.display import HTML, Javascript, display

from ...ui import get_viewer_html, get_viewer_js


def visualize_properties(results, width=900, title="Properties", extra_config=None):
    """
    Visualize properties using a Prove viewer.

    Args:
        results: List[dict] of property JSON objects (or a single dict).
        width: Container width in pixels.
        title: Title displayed above the viewer.
        extra_config: Optional dict with materials, components, callbacks, etc.
    """
    if isinstance(results, dict):
        results = [results]

    DATA_KEYS = {"value", "values", "xDataArray"}
    results = [r for r in results if DATA_KEYS & r.keys()]

    timestamp = time.time()
    div_id = f"prove-{timestamp}"
    results_json = json.dumps(results)
    extra_config_json = json.dumps(extra_config) if extra_config else "undefined"

    html = get_viewer_html(
        div_id=div_id,
        width=width,
        title=title,
        custom_styles="border:1px solid #ddd; padding:12px; background:#fff; color:#111;",
    )
    js = get_viewer_js(
        data_json=results_json,
        div_id=div_id,
        bundle_url="https://mat3ra.github.io/prove/main.js",
        render_function="renderResults",
        data_var_name="results",
        extra_config_json=extra_config_json,
    )

    display(HTML(html))
    display(Javascript(js))
