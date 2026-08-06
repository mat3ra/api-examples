import json
import os
import re
import sys
from typing import List, Tuple, Union

import yaml  # type: ignore

from ...primitive.environment import ENVIRONMENT
from ...primitive.logger import log

try:
    import micropip  # type: ignore
except ImportError:
    micropip = None  # type: ignore

NODEPS_PREFIX = "nodeps:"
URL_PREFIXES = ("http://", "https://", "emfs:/")
VERSION_SPECIFIERS = ("==", ">=", "<=", "!=", "~=", ">", "<")


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


def is_url_package(pkg: str) -> bool:
    return pkg.startswith(URL_PREFIXES)


def remove_nodeps_prefix(pkg: str) -> str:
    return pkg.replace(NODEPS_PREFIX, "", 1) if pkg.startswith(NODEPS_PREFIX) else pkg


def package_has_version_specifier(pkg: str) -> bool:
    spec = remove_nodeps_prefix(pkg)
    return any(op in spec for op in VERSION_SPECIFIERS)


def should_reinstall_package(pkg: str, previous_packages: List[str]) -> bool:
    package_name = get_package_name(pkg)
    if not package_name or not package_has_version_specifier(pkg) or is_url_package(remove_nodeps_prefix(pkg)):
        return False
    previous_spec = next((item for item in previous_packages if get_package_name(item) == package_name), None)
    return previous_spec is not None and previous_spec != pkg


def get_package_name(pkg: str) -> Union[str, None]:
    spec = remove_nodeps_prefix(pkg)
    match = re.match(r"^[A-Za-z0-9_.-]+", spec)
    return match.group(0) if match else None


def get_import_package_name(package_name: str) -> str:
    return package_name.replace("-", "_")


def clear_imported_package_modules(package_name: str):
    import_name = get_import_package_name(package_name)
    module_names = [name for name in sys.modules if name == import_name or name.startswith(f"{import_name}.")]
    for module_name in module_names:
        sys.modules.pop(module_name, None)


async def uninstall_package_pyodide(pkg: str):
    package_name = get_package_name(pkg)
    if not package_name:
        return
    if not hasattr(micropip, "uninstall"):
        raise RuntimeError(f"Cannot reinstall {package_name}: micropip.uninstall is unavailable.")

    uninstall_result = micropip.uninstall(package_name)
    if hasattr(uninstall_result, "__await__"):
        await uninstall_result
    clear_imported_package_modules(package_name)


def get_install_spec_and_deps(pkg: str) -> Tuple[str, bool]:
    if pkg.startswith(NODEPS_PREFIX):
        return remove_nodeps_prefix(pkg), False
    return pkg, not is_url_package(pkg)


async def install_package_pyodide(pkg: str, verbose: bool = True, reinstall: bool = False):
    """
    Install a package in a Pyodide environment.

    Args:
        pkg (str): The name of the package to install. Can be prefixed with 'nodeps:' to skip dependencies.
        verbose (bool): Whether to print the name of the installed package.

    Examples:
        await install_package_pyodide("numpy")  # installs with deps
        await install_package_pyodide("nodeps:e3nn==0.4.4")  # installs without deps
    """
    pkg, are_dependencies_installed = get_install_spec_and_deps(pkg)
    if reinstall:
        await uninstall_package_pyodide(pkg)

    await micropip.install(pkg, deps=are_dependencies_installed)
    pkg_name = pkg.split("/")[-1].split("-")[0] if "://" in pkg else pkg.split("==")[0]
    if verbose:
        log(f"Installed {pkg_name}", force_verbose=verbose)


async def install_packages_pyodide(notebook_name_pattern: str, verbose: bool = True):
    """
    Install the given packages, skipping if the list is unchanged since last run.

    Args:
        notebook_name_pattern (str): Pattern matched against notebook names in config.yml.
        verbose (bool): Whether to print the names of the installed packages.
    """
    packages = await get_package_list_from_config(get_config_yml_file_path(""), notebook_name_pattern)
    requirements_hash = str(hash(json.dumps(packages)))
    previous_hash = os.environ.get("requirements_hash")
    previous_packages = json.loads(os.environ.get("requirements_packages", "[]"))
    if should_install_packages(previous_hash, requirements_hash):
        for pkg in packages:
            await install_package_pyodide(
                pkg,
                verbose,
                reinstall=should_reinstall_package(pkg, previous_packages),
            )
        if verbose:
            log("Packages installed successfully.", force_verbose=verbose)
        os.environ["requirements_hash"] = requirements_hash
        os.environ["requirements_packages"] = json.dumps(packages)
    else:
        if verbose:
            log("Packages are already installed.", force_verbose=verbose)
