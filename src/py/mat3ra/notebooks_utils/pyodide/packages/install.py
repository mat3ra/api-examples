"""Pyodide package installer with IndexedDB wheel caching.

On first install, packages are downloaded from PyPI and cached in IndexedDB.
On subsequent kernel starts, cached wheels are written to emfs and installed
locally — eliminating network downloads.
"""

import json
import os
import re
import sys
import time
from typing import List, Tuple, Union

from ...primitive.environment import ENVIRONMENT
from ...primitive.logger import log
from ..io import read_from_url_pyodide, write_to_file
from . import wheel_cache

try:
    import micropip  # type: ignore
except ImportError:
    micropip = None  # type: ignore

NODEPS_PREFIX = "nodeps:"
URL_PREFIXES = ("http://", "https://", "emfs:/")
LOCAL_URL_PREFIXES = ("emfs:/",)
REMOTE_URL_PREFIXES = ("http://", "https://")
VERSION_SPECIFIERS = ("==", ">=", "<=", "!=", "~=", ">", "<")

WHEEL_CACHE_EMFS_DIRECTORY = "/tmp/wheel_cache"


def get_config_yml_file_path(config_file_path: str) -> str:
    """
    Resolve the absolute path to the config.yml file.

    Args:
        config_file_path (str): Relative path override; empty string uses the JupyterLite default (/drive/config.yml).

    Returns:
        str: Absolute path to the config file.
    """
    config_file_full_path = os.path.normpath(os.path.join("/drive/", "./config.yml"))
    if config_file_path != "":
        config_file_full_path = os.path.normpath(os.path.join(os.getcwd(), config_file_path))
    return config_file_full_path


async def read_config_into_dict(config_file_path: str) -> dict:
    with open(get_config_yml_file_path(config_file_path), "r") as f:
        # NOTE: PyYAML (yaml) is preinstalled at the JupyterLite build level as a required
        # environment requirement. The import is placed inside this function (rather than
        # at the top level of the module) to prevent any potential boot/load order issues
        # during fresh kernel initialization.
        # import micropip  # type: ignore
        #
        # await micropip.install("pyyaml")
        import yaml  # type: ignore

        requirements_dict = yaml.safe_load(f)

    return requirements_dict


def get_packages_list(requirements_dict: dict, notebook_name_pattern: str = "") -> List[str]:
    """
    Get the list of packages to install based on the requirements dict.

    Args:
        requirements_dict (dict): The dictionary containing the requirements.
        notebook_name_pattern (str): The pattern of the notebook name.

    Returns:
        List[str]: The list of packages to install.
    """
    packages_default_common = requirements_dict.get("default", {}).get("packages_common", [])
    packages_default_environment_specific = requirements_dict.get("default", {}).get(
        f"packages_{ENVIRONMENT.value}", []
    )

    matching_notebook_requirements_list = [
        cfg for cfg in requirements_dict.get("notebooks", []) if re.search(cfg.get("name"), notebook_name_pattern)
    ]
    packages_notebook_common = []
    packages_notebook_environment_specific = []

    for notebook_requirements in matching_notebook_requirements_list:
        packages_common = notebook_requirements.get("packages_common", [])
        packages_environment_specific = notebook_requirements.get(f"packages_{ENVIRONMENT.value}", [])
        if packages_common:
            packages_notebook_common.extend(packages_common)
        if packages_environment_specific:
            packages_notebook_environment_specific.extend(packages_environment_specific)

    # Note: environment specific packages have to be installed first,
    # because in Pyodide common packages might depend on them
    return deduplicate_packages(
        [
            *packages_default_environment_specific,
            *packages_notebook_environment_specific,
            *packages_default_common,
            *packages_notebook_common,
        ]
    )


def deduplicate_packages(packages: List[str]) -> List[str]:
    return list(dict.fromkeys(packages))


async def get_package_list_from_config(config_file_path: str, notebook_name_pattern: str) -> list:
    requirements_dict = await read_config_into_dict(config_file_path)
    packages = get_packages_list(requirements_dict, notebook_name_pattern)
    return packages


def should_install_packages(previous_hash: Union[str, None], requirements_hash: str) -> bool:
    return previous_hash != requirements_hash


def is_url_package(package_spec: str) -> bool:
    return package_spec.startswith(URL_PREFIXES)


def is_local_url_package(package_spec: str) -> bool:
    return package_spec.startswith(LOCAL_URL_PREFIXES)


def is_remote_url_package(package_spec: str) -> bool:
    return package_spec.startswith(REMOTE_URL_PREFIXES)


def remove_nodeps_prefix(package_spec: str) -> str:
    return package_spec.replace(NODEPS_PREFIX, "", 1) if package_spec.startswith(NODEPS_PREFIX) else package_spec


def package_has_version_specifier(package_spec: str) -> bool:
    spec = remove_nodeps_prefix(package_spec)
    return any(op in spec for op in VERSION_SPECIFIERS)


def should_reinstall_package(package_spec: str, profile_changed: bool) -> bool:
    return (
        profile_changed
        and package_has_version_specifier(package_spec)
        and not is_url_package(remove_nodeps_prefix(package_spec))
    )


def get_package_name(package_spec: str) -> Union[str, None]:
    spec = remove_nodeps_prefix(package_spec)
    match = re.match(r"^[A-Za-z0-9_.-]+", spec)
    return match.group(0) if match else None


def get_import_package_name(package_name: str) -> str:
    return package_name.replace("-", "_")


def get_display_name(package_spec: str) -> str:
    if "://" in package_spec:
        return package_spec.split("/")[-1].split("-")[0]
    return package_spec.split("==")[0]


def clear_imported_package_modules(package_name: str):
    import_name = get_import_package_name(package_name)
    module_names = [name for name in sys.modules if name == import_name or name.startswith(f"{import_name}.")]
    for module_name in module_names:
        sys.modules.pop(module_name, None)


async def uninstall_package_pyodide(package_spec: str):
    package_name = get_package_name(package_spec)
    if not package_name:
        return
    if not hasattr(micropip, "uninstall"):
        raise RuntimeError(f"Cannot reinstall {package_name}: micropip.uninstall is unavailable.")

    uninstall_result = micropip.uninstall(package_name)
    if hasattr(uninstall_result, "__await__"):
        await uninstall_result
    clear_imported_package_modules(package_name)


def get_install_spec_and_deps(package_spec: str) -> Tuple[str, bool]:
    if package_spec.startswith(NODEPS_PREFIX):
        return remove_nodeps_prefix(package_spec), False
    return package_spec, not is_url_package(package_spec)


def get_cache_key(package_spec: str) -> str:
    """
    Normalize a package spec into a cache key.
    """
    spec = remove_nodeps_prefix(package_spec)
    return spec.lower().strip()


async def install_package_pyodide(
    package_spec: str,
    verbose: bool = True,
    reinstall: bool = False,
    use_cache: bool = True,
):
    """
    Install a package in a Pyodide environment, using wheel cache when possible.

    Args:
        package_spec: Package name, version spec, or URL. Can be prefixed with 'nodeps:'.
        verbose: Whether to log the installed package name.
        reinstall: Whether to uninstall first.
        use_cache: Whether to use the IndexedDB wheel cache.
    """
    raw_spec, are_dependencies_installed = get_install_spec_and_deps(package_spec)

    if reinstall:
        await uninstall_package_pyodide(raw_spec)

    installed_from_cache = False

    if use_cache and is_remote_url_package(raw_spec):
        installed_from_cache = await _install_from_cache_or_download(raw_spec, are_dependencies_installed)

    if not installed_from_cache:
        await micropip.install(raw_spec, deps=are_dependencies_installed)

    if verbose:
        log(f"Installed {get_display_name(raw_spec)}", force_verbose=verbose)


async def _install_from_cache_or_download(url: str, install_dependencies: bool) -> bool:
    """
    Try to install from cache; if miss, download, cache, and install. Returns True on success.
    """
    try:
        # Cache key is the full URL, which ensures that if a new version is published
        # to PyPI, the URL will change and the cache will automatically invalidate.
        cache_key = url
        filename = url.split("/")[-1].split("?")[0]

        # Micropip requires a physical filepath or a web URL to perform installation;
        # it cannot install directly from in-memory bytes. Therefore, we write the
        # wheel bytes to Pyodide's local EMFS (Emscripten File System) temp directory first.
        os.makedirs(WHEEL_CACHE_EMFS_DIRECTORY, exist_ok=True)
        emfs_path = os.path.join(WHEEL_CACHE_EMFS_DIRECTORY, filename)

        # 1. Attempt to hit the persistent IndexedDB cache.
        cached_bytes = await wheel_cache.get_cached_wheel(cache_key)

        if cached_bytes is not None:
            # Cache Hit: Write in-memory bytes to EMFS and install locally (fast restart).
            await write_to_file(emfs_path, cached_bytes)
            await micropip.install(emfs_path, deps=install_dependencies)
            return True

        # 2. Cache Miss: Download from the remote URL, store in IndexedDB, and write to EMFS.
        wheel_bytes = await read_from_url_pyodide(url, as_bytes=True)
        if not isinstance(wheel_bytes, bytes):
            raise TypeError("Expected bytes from read_from_url_pyodide")
        await wheel_cache.put_cached_wheel(cache_key, wheel_bytes)

        await write_to_file(emfs_path, wheel_bytes)
        await micropip.install(emfs_path, deps=install_dependencies)

        # 3. Update the cache manifest with the newly added package metadata.
        manifest = await wheel_cache.read_manifest()
        manifest[cache_key] = {
            "filename": filename,
            "size": len(wheel_bytes),
            "cached_at": time.time(),
        }
        await wheel_cache.write_manifest(manifest)

        return True
    except Exception:
        # If any part of the cache system fails (DB error, disk full), fail gracefully and
        # let the caller fall back to micropip's default remote HTTP installer.
        return False


async def install_packages_pyodide(
    notebook_name_pattern: str,
    verbose: bool = True,
    force: bool = False,
    use_cache: bool = True,
):
    """
    Install packages from config.yml, using IndexedDB wheel cache for persistence.

    Args:
        notebook_name_pattern: Pattern matched against notebook names in config.yml.
        verbose: Whether to log install progress.
        force: Clear the wheel cache and reinstall everything from network.
        use_cache: Whether to use the IndexedDB wheel cache (default True).
    """
    if force and use_cache:
        # A forced reinstall clears the whole wheel cache first to guarantee downloading
        # the latest packages and dependencies from PyPI.
        await wheel_cache.clear_cache()
        if verbose:
            log("Wheel cache cleared.", force_verbose=verbose)

    # 1. Resolve and hash the list of packages specified for this notebook profile.
    packages = await get_package_list_from_config(get_config_yml_file_path(""), notebook_name_pattern)
    requirements_hash = str(hash(json.dumps(packages)))

    # 2. Check if this profile's packages have already been installed in this session.
    #    os.environ contains volatile session state which is lost on kernel restart.
    previous_hash = os.environ.get("requirements_hash")

    # 3. If this is a fresh kernel session (os.environ is empty) and caching is enabled,
    #    we read the persistent hash from IndexedDB. This prevents redundant reinstall
    #    checks across kernel restarts.
    if use_cache and previous_hash is None:
        manifest = await wheel_cache.read_manifest()
        previous_hash = manifest.get("_requirements_hash")

    profile_changed = previous_hash is not None and previous_hash != requirements_hash

    # 4. Trigger installation if either:
    #    a) The profile is different or has never been run (previous_hash != requirements_hash)
    #    b) Force install was explicitly requested (force=True)
    if should_install_packages(previous_hash, requirements_hash) or force:
        for package_spec in packages:
            await install_package_pyodide(
                package_spec,
                verbose,
                reinstall=should_reinstall_package(package_spec, profile_changed),
                use_cache=use_cache,
            )

        if verbose:
            log("Packages installed successfully.", force_verbose=verbose)

        # 5. Persist the new requirements hash both in volatile memory (for this session)
        #    and in persistent storage (for subsequent kernel restarts).
        os.environ["requirements_hash"] = requirements_hash

        if use_cache:
            manifest = await wheel_cache.read_manifest()
            manifest["_requirements_hash"] = requirements_hash
            await wheel_cache.write_manifest(manifest)
    else:
        # If the package profile matches perfectly, we skip micropip entirely,
        # ensuring instant start times for the user.
        if verbose:
            log("Packages are already installed.", force_verbose=verbose)
