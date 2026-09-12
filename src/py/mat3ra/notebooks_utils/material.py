from .core.entity.material.io import get_materials, load_material_from_folder, load_materials_from_folder, set_materials

__all__ = [  # noqa: F822 -- label_interface_parts is provided lazily via __getattr__ below
    "get_materials",
    "set_materials",
    "load_materials_from_folder",
    "load_material_from_folder",
    "label_interface_parts",
]


def __getattr__(name):
    # Lazy: label_interface_parts pulls in mat3ra.made, a dependency most importers of this
    # module (e.g. the structure notebook's set_materials/load_material_from_folder use) do not need.
    if name == "label_interface_parts":
        from .core.entity.material.interface import label_interface_parts

        return label_interface_parts
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
