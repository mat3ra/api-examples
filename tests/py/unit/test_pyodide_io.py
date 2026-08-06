import json
from types import SimpleNamespace
from unittest.mock import patch

from mat3ra.notebooks_utils.pyodide.io import send_data_pyodide, set_data_pyodide


def test_send_data_pyodide_calls_same_page_bridge_directly():
    received = []
    with patch("mat3ra.notebooks_utils.pyodide.io.JSON", SimpleNamespace(parse=json.loads)):
        with patch("mat3ra.notebooks_utils.pyodide.io.sendDataToHost", received.append):
            send_data_pyodide({"syncScope": "python-repl", "entities": []})

    assert received == [{"syncScope": "python-repl", "entities": []}]


def test_send_data_pyodide_uses_display_for_jupyterlite():
    with patch("mat3ra.notebooks_utils.pyodide.io.JSON", None):
        with patch("mat3ra.notebooks_utils.pyodide.io.Javascript", side_effect=lambda source: source):
            with patch("mat3ra.notebooks_utils.pyodide.io.display") as display:
                send_data_pyodide({"syncScope": "python-repl", "entities": []})

    assert display.call_args.args[0] == 'window.sendDataToHost({"syncScope": "python-repl", "entities": []});'


def test_set_data_pyodide_updates_python_data():
    with patch("mat3ra.notebooks_utils.pyodide.io.JSON", SimpleNamespace(parse=json.loads)):
        with patch("mat3ra.notebooks_utils.pyodide.io.sendDataToHost"):
            with patch("mat3ra.notebooks_utils.pyodide.io.set_data_python") as set_data_python:
                set_data_pyodide("materials", [{"name": "Si"}])

    set_data_python.assert_called_once_with("materials", [{"name": "Si"}])
