import io
import json
import os
from typing import Any, Dict, Optional, Union

from ..core.io import set_data_python
from ..primitive.logger import log

try:
    from IPython.display import Javascript, display
except ImportError:
    Javascript = None
    display = None

try:
    from js import JSON, sendDataToHost  # type: ignore
except ImportError:
    JSON = None
    sendDataToHost = None

try:
    from pyodide.http import pyfetch  # type: ignore
except ImportError:
    pyfetch = None


async def read_from_url_pyodide(url: str, as_bytes: bool = False) -> Union[str, bytes]:
    """
    Fetch and read content from a URL in a Pyodide environment.

    Args:
        url (str): The URL to fetch from.
        as_bytes (bool): Whether to return the content as bytes.

    Returns:
        str or bytes: The content.
    """
    if pyfetch is None:
        raise RuntimeError("pyfetch is available only in Pyodide")

    response = await pyfetch(url)
    if as_bytes:
        return await response.bytes()
    return await response.string()


def send_data_pyodide(payload: Dict[str, Any]):
    """Send a bridge payload to the host application."""
    serialized_data = json.dumps(payload)

    if JSON is not None and sendDataToHost is not None:
        sendDataToHost(JSON.parse(serialized_data))
        return

    if Javascript is None or display is None:
        raise RuntimeError("IPython is required to send data from JupyterLite")

    display(Javascript(f"window.sendDataToHost({serialized_data});"))


def set_data_pyodide(key: str, value: Any):
    """
    Take a Python object, serialize it to JSON, and send it to the host environment
    through a JavaScript function defined in the JupyterLite extension `data_bridge`.

    Args:
        key (str): The name under which data will be sent.
        value (Any): The value to send to the host environment.
    """
    send_data_pyodide({key: value})
    log(f"Data for {key} sent to host.")
    set_data_python(key, value)


def get_data_pyodide(key: str, globals_dict: Optional[Dict] = None):
    """
    Load data from the host environment into globals()[key] variable.

    Args:
        key (str): Global variable name to store the received data.
        globals_dict (dict, optional): globals() dictionary of the current scope.
    """
    if globals_dict is not None:
        globals_dict[key] = globals_dict.get("data_from_host", None)


async def write_to_file(file_name: str, file_content, mode: str = "wb"):
    """
    Write content to a file, handling both Python and Pyodide environments.

    Args:
        file_name (str): The name of the file to write.
        file_content (str | bytes | io.StringIO | io.BytesIO): The content to write.
        mode (str): The mode to open the file in. Defaults to "wb" (write bytes).

    Returns:
        str: The absolute path of the saved file.
    """
    if isinstance(file_content, io.StringIO):
        file_content = file_content.getvalue().encode("utf-8")
    elif isinstance(file_content, io.BytesIO):
        file_content = file_content.getvalue()

    if "b" in mode and isinstance(file_content, str):
        file_content = file_content.encode("utf-8")

    with open(file_name, mode) as file:
        file.write(file_content)

    return os.path.abspath(file_name)
