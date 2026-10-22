"""Install notebook dependencies from config.yml.

Routes to the appropriate backend: micropip (Pyodide) or pip (Python).
In Pyodide, downloaded wheels are cached in IndexedDB so subsequent
kernel restarts skip network downloads.
"""

from .ipython.packages.install import install_packages_python
from .primitive.environment import is_pyodide_environment


async def install_packages(
    notebook_name_pattern: str,
    config_file_path: str = "",
    verbose: bool = True,
    force: bool = False,
    use_cache: bool = True,
):
    """Install the packages listed in config.yml for the given notebook name pattern.

    Usage in notebooks:
        from mat3ra.notebooks_utils.packages import install_packages
        await install_packages("my_notebook")

    Args:
        notebook_name_pattern: Pattern matched against notebook names in config.yml.
        config_file_path: Path to config.yml; empty string uses the JupyterLite default.
        verbose: Whether to print install progress.
        force: Clear wheel cache and reinstall from network (Pyodide only).
        use_cache: Use IndexedDB wheel cache for faster restarts (Pyodide only, default True).
    """
    if is_pyodide_environment():
        from .pyodide.packages.install import install_packages_pyodide

        await install_packages_pyodide(notebook_name_pattern, verbose, force=force, use_cache=use_cache)
    else:
        install_packages_python(notebook_name_pattern, verbose)
