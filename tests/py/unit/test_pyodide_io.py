import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

from mat3ra.notebooks_utils.pyodide.io import send_data_pyodide, set_data_pyodide


def test_send_data_pyodide_calls_same_page_bridge_directly():
    received = []
    javascript = SimpleNamespace(
        JSON=SimpleNamespace(parse=json.loads),
        sendDataToHost=received.append,
    )

    with patch.dict(sys.modules, {"js": javascript}):
        send_data_pyodide({"syncScope": "python-repl", "entities": []})

    assert received == [{"syncScope": "python-repl", "entities": []}]


def test_set_data_pyodide_keeps_the_jupyterlite_display_fallback():
    with patch.dict(sys.modules, {"js": None}):
        with patch("IPython.display.Javascript", side_effect=lambda source: source):
            with patch("IPython.display.display") as display:
                with patch("mat3ra.notebooks_utils.pyodide.io.set_data_python"):
                    set_data_pyodide("materials", [{"name": "Si"}])

    rendered_source = display.call_args.args[0]
    assert "window.sendDataToHost" in rendered_source
    assert '"materials": [{"name": "Si"}]' in rendered_source
