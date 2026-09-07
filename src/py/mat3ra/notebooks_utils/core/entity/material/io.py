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
        index = 0
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
                name = os.path.splitext(filename)[0]
                log(f"{index}: {name}", SeverityLevelEnum.INFO, force_verbose=verbose)
                index += 1
                data_from_host.append(data)
    except FileNotFoundError:
        log(f"No data found in the '{folder_path}' folder.", SeverityLevelEnum.ERROR, force_verbose=verbose)
        return []

    try:
        materials = [MaterialWithBuildMetadata.create(item) for item in data_from_host]
    except Exception:
        materials = [Material.create(item) for item in data_from_host]

    if materials:
        log(
            f"Successfully loaded {len(materials)} materials from folder '{folder_path}'",
            SeverityLevelEnum.INFO,
            force_verbose=verbose,
        )
    else:
        log(f"No materials found in folder '{folder_path}'", SeverityLevelEnum.WARNING, force_verbose=verbose)

    return materials


def load_material_from_folder(folder_path: str, name: str, verbose: bool = True) -> Optional[Any]:
    """
    Load a single material from the specified folder by matching a substring of the name or filename.

    Args:
        folder_path (str): The path to the folder containing material files.
        name (str): The substring to match against material names or filenames (case-insensitive).
        verbose (bool): Whether to log verbose messages.

    Returns:
        Optional[Material]: The first Material object that matches, or None if not found.
    """
    name_lower = name.lower()
    resulting_material = None

    for filename in sorted(os.listdir(folder_path)):
        if filename.endswith(".json") and name_lower in os.path.splitext(filename)[0].lower():
            with open(os.path.join(folder_path, filename), "r") as file:
                data = json.load(file)
            try:
                resulting_material = MaterialWithBuildMetadata.create(data)
            except Exception:
                resulting_material = Material.create(data)
            break

    if not resulting_material:
        materials = load_materials_from_folder(folder_path, verbose=verbose)
        for material in materials:
            if name_lower in material.name.lower():
                resulting_material = material
                break

    if resulting_material:
        log(f"Found: '{resulting_material.name}'", SeverityLevelEnum.INFO, force_verbose=verbose)
        return resulting_material

    log(f"No material containing '{name}' found in '{folder_path}'.", SeverityLevelEnum.WARNING, force_verbose=verbose)
    return None
