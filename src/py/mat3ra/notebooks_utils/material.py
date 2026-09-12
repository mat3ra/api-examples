from typing import Container

from mat3ra.made.material import Material
from mat3ra.made.tools.convert.interface_parts_enum import InterfacePartsEnum

from .core.entity.material.io import get_materials, load_material_from_folder, load_materials_from_folder, set_materials

__all__ = [
    "get_materials",
    "set_materials",
    "load_materials_from_folder",
    "load_material_from_folder",
    "label_interface_parts",
]


def label_interface_parts(material: Material, substrate_elements: Container[str]) -> Material:
    """Labels each atom SUBSTRATE or FILM by whether its element is in `substrate_elements`."""
    labels = [
        InterfacePartsEnum.SUBSTRATE.value if element in substrate_elements else InterfacePartsEnum.FILM.value
        for element in material.basis.elements.values
    ]
    material.basis.set_labels_from_list(labels)
    return material
