import json

from IPython.display import Javascript, display


def download_content_to_file(content: dict, filename: str):
    """
    Download content to a file with the given filename.

    Args:
        content (dict): The content to download.
        filename (str): The name of the file to download.
    """
    if isinstance(content, dict):
        content_str = json.dumps(content, indent=4)
    else:
        content_str = str(content)

    js_code = f"""
    var content = `{content_str}`;
    var filename = `{filename}`;
    var blob = new Blob([content], {{ type: 'application/json' }});
    var link = document.createElement('a');
    link.href = window.URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    """
    display(Javascript(js_code))
