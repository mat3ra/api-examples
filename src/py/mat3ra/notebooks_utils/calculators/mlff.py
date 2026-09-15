from importlib import import_module
from typing import Any, Dict

MLFF_MODULES = {
    "mace": ("mat3ra.notebooks_utils.pyodide.packages.mace", "create_mace_calculator"),
    "uma": ("mat3ra.notebooks_utils.pyodide.packages.uma", "create_uma_calculator"),
    "mattersim": ("mat3ra.notebooks_utils.pyodide.packages.mattersim", "create_mattersim_calculator"),
    "nequip": ("mat3ra.notebooks_utils.pyodide.packages.nequip", "create_nequip_calculator"),
}


def get_mlff_install_profiles(mlff_name: str) -> str:
    mlff = (mlff_name or "").strip().lower()
    if mlff in MLFF_MODULES:
        return f"made|api_examples|torch|mlff|{mlff}"
    raise ValueError(f"Unsupported MLFF: {mlff_name!r}")


def create_mlff_calculator(mlff_name: str, settings: Dict[str, Any]):
    mlff = (mlff_name or "").strip().lower()
    if mlff not in MLFF_MODULES:
        raise ValueError(f"Unsupported MLFF: {mlff_name!r}")

    module_name, factory_name = MLFF_MODULES[mlff]
    module = import_module(module_name)
    factory = getattr(module, factory_name)
    return factory(**settings)
