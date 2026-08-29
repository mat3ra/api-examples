from typing import Any, Dict, Optional, Union

from .core.io import get_data_python, read_from_url_python, set_data_python
from .ipython.io import download_content_to_file
from .primitive.enums import EnvironmentsEnum
from .primitive.environment import ENVIRONMENT
from .pyodide.io import get_data_pyodide, read_from_url_pyodide, send_data_pyodide, set_data_pyodide
from .settings import UPLOADS_FOLDER


def get_data(key: str, globals_dict: Optional[Dict] = None):
    """
    Switch between the two functions `get_data_pyodide` and `get_data_python` based on the environment.

    Args:
        key (str): The name under which data is expected to be received.
        globals_dict (dict, optional): A dictionary to store the received data. Defaults to None.
    """
    if ENVIRONMENT == EnvironmentsEnum.PYODIDE:
        get_data_pyodide(key, globals_dict)
    elif ENVIRONMENT == EnvironmentsEnum.PYTHON:
        get_data_python(key, globals_dict)


def set_data(key: str, value: Any, folder_path: str = UPLOADS_FOLDER):
    """
    Switch between the two functions `set_data_pyodide` and `set_data_python` based on the environment.

    Args:
        key (str): The name under which data will be written or sent.
        value (Any): The value to write or send.
        folder_path (str, optional): The folder path to use for writing data.
    """
    if ENVIRONMENT == EnvironmentsEnum.PYODIDE:
        set_data_pyodide(key, value)
    elif ENVIRONMENT == EnvironmentsEnum.PYTHON:
        set_data_python(key, value, folder_path=folder_path)


def send_data(payload: Dict[str, Any]):
    """Send a complete bridge payload. This operation is meaningful only in Pyodide."""
    if ENVIRONMENT == EnvironmentsEnum.PYODIDE:
        send_data_pyodide(payload)


async def read_from_url(url: str, as_bytes: bool = False) -> Union[str, bytes]:
    """
    Read content from a URL, routing to the pyodide or Python implementation.

    Args:
        url (str): The URL to fetch from.
        as_bytes (bool): Whether to return the content as bytes.

    Returns:
        str or bytes: The content.
    """
    if ENVIRONMENT == EnvironmentsEnum.PYODIDE:
        return await read_from_url_pyodide(url, as_bytes)
    return read_from_url_python(url, as_bytes)


__all__ = ["download_content_to_file", "get_data", "read_from_url", "send_data", "set_data"]
