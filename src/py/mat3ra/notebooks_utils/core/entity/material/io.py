import inspect
import json
import os
from typing import Any, List, Optional

from mat3ra.made.material import Material
from mat3ra.made.tools.build_components import MaterialWithBuildMetadata
from mat3ra.utils.array import convert_to_array_if_not

from ....io import get_data, set_data
from ....primitive.enums import SeverityLevelEnum
from ....primitive.logger import log
from ....settings import UPLOADS_FOLDER


def get_materials(globals_dict: Optional[dict] = None) -> List[Any]:
    """
    Retrieve materials from the environment and assign them to globals_dict["materials_in"].

    Args:
        globals_dict (dict, optional): The globals dictionary to populate.

    Returns:
        List[Material]: A list of Material objects.
    """
    if globals_dict is None:
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back  # type: ignore
            caller_globals = caller_frame.f_globals  # type: ignore
            globals_dict = caller_globals
        finally:
            del frame  # Avoid reference cycles
    get_data("materials_in", globals_dict)

    if "materials_in" in globals_dict and globals_dict["materials_in"]:
        materials = []
        for item in globals_dict["materials_in"]:
            try:
                materials.append(MaterialWithBuildMetadata.create(item))
            except Exception:
                materials.append(Material.create(item))
        log(f"Retrieved {len(materials)} materials.")
        return materials
    else:
        log(f"No input materials found. Loading from the {UPLOADS_FOLDER} folder.")
        return load_materials_from_folder()


def set_materials(materials: List[Any], folder_path: str = UPLOADS_FOLDER):
    """
    Serialize and send a list of Material objects to the environment.

    Args:
        materials (List[Material]): The list of Material objects to send.
    """

    materials = convert_to_array_if_not(materials)
    materials_data = [json.loads(material.to_json()) for material in materials]
    set_data("materials", materials_data, folder_path=folder_path)
    log(
        f"Successfully sent {len(materials)} materials to the environment.",
        SeverityLevelEnum.INFO,
    )


def load_materials_from_folder(folder_path: Optional[str] = None, verbose: bool = True) -> List[Any]:
    """
    Load materials from the specified folder or from the UPLOADS_FOLDER by default.

    Args:
        folder_path (Optional[str]): The path to the folder containing material files.
                                     If not provided, defaults to the UPLOADS_FOLDER.
        verbose (bool): Whether to log verbose messages.

    Returns:
        List[Material]: A list of Material objects loaded from the folder.
    """
    folder_path = folder_path or UPLOADS_FOLDER

    if not os.path.exists(folder_path):
        log(f"Folder '{folder_path}' does not exist.", SeverityLevelEnum.ERROR, force_verbose=verbose)
        return []

    data_from_host = []
    try:
        for filename in sorted(os.listdir(folder_path)):
            if filename.endswith(".json"):
                file_path = os.path.join(folder_path, filename)
                try:
                    with open(file_path, "r") as file:
                        data = json.load(file)
                except (json.JSONDecodeError, OSError) as error:
                    log(
                        f"Skipping invalid JSON file '{file_path}': {error}",
                        SeverityLevelEnum.WARNING,
                        force_verbose=verbose,
                    )
                    continue
                data_from_host.append((os.path.splitext(filename)[0], data))
    except FileNotFoundError:
        log(f"No data found in the '{folder_path}' folder.", SeverityLevelEnum.ERROR, force_verbose=verbose)
        return []

    materials: List[Any] = []
    for name, config in data_from_host:
        if not MaterialWithBuildMetadata.is_valid(config):
            log(f"Skipping '{name}.json': not a material.", SeverityLevelEnum.WARNING, force_verbose=verbose)
            continue
        log(f"{len(materials)}: {name}", SeverityLevelEnum.INFO, force_verbose=verbose)
        materials.append(MaterialWithBuildMetadata.create(config))

    if materials:
        log(
            f"Successfully loaded {len(materials)} materials from folder '{folder_path}'",
            SeverityLevelEnum.INFO,
            force_verbose=verbose,
        )
    else:
        log(f"No materials found in folder '{folder_path}'", SeverityLevelEnum.WARNING, force_verbose=verbose)

    return materials


def _get_name_match_rank(requested_name: str, material_name: str, filename_without_extension: str) -> Optional[int]:
    """
    Rank how well one folder entry matches a requested name: lower is better, None is no match.

    An exact match wins over a substring match, and a case-sensitive match over a case-insensitive
    one. Among exact matches the material name wins; among substring matches the filename wins.
    """
    requested_name_lower = requested_name.lower()
    ranked_candidates = [
        material_name == requested_name,
        filename_without_extension == requested_name,
        material_name.lower() == requested_name_lower,
        filename_without_extension.lower() == requested_name_lower,
        requested_name_lower in filename_without_extension.lower(),
        requested_name_lower in material_name.lower(),
    ]
    return next((rank for rank, matches in enumerate(ranked_candidates) if matches), None)


def load_material_from_folder(folder_path: str, name: str, verbose: bool = True) -> Optional[Any]:
    """
    Load a single material from the specified folder by matching the name or filename.

    Args:
        folder_path (str): The path to the folder containing material files.
        name (str): The name to match against material names or filenames. An exact match is
                    preferred; otherwise a case-insensitive substring match is accepted.
        verbose (bool): Whether to log verbose messages.

    Returns:
        Optional[Material]: The best matching Material object, or None if not found.
    """
    best_rank = None
    resulting_material = None

    for filename in sorted(os.listdir(folder_path)):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(folder_path, filename), "r") as file:
            data = json.load(file)
        if not MaterialWithBuildMetadata.is_valid(data):
            continue
        material = MaterialWithBuildMetadata.create(data)
        rank = _get_name_match_rank(name, material.name, os.path.splitext(filename)[0])
        if rank is not None and (best_rank is None or rank < best_rank):
            best_rank, resulting_material = rank, material

    if resulting_material:
        log(f"Found: '{resulting_material.name}'", SeverityLevelEnum.INFO, force_verbose=verbose)
        return resulting_material

    log(f"No material containing '{name}' found in '{folder_path}'.", SeverityLevelEnum.WARNING, force_verbose=verbose)
    return None
