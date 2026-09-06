from typing import List, Optional, Tuple

import numpy as np
from mat3ra.made.material import Material
from mat3ra.made.tools.convert.interface_parts_enum import InterfacePartsEnum
from mat3ra.made.tools.modify import interface_get_part

LAYER_TOLERANCE = 0.5  # Angstrom


def _cartesian_coordinates(material: Material) -> np.ndarray:
    cartesian = material.clone()
    cartesian.to_cartesian()
    return np.array(cartesian.basis.coordinates.values)


def get_corrugation(material: Material) -> float:
    """Height spread of a material's atoms, in Angstrom — the buckling of an adsorbed film."""
    heights = _cartesian_coordinates(material)[:, 2]
    return float(heights.max() - heights.min())


def get_interface_separation(interface: Material, substrate_elements: Optional[List[str]] = None) -> float:
    """
    Distance between the film and the substrate, in Angstrom.

    Measured from the film's mean height to the substrate's top layer — the convention published
    structure data uses for a film that buckles.

    Args:
        interface: The interface structure.
        substrate_elements: Which elements are the substrate. Give these for a structure that has
            been through a relaxation or file round-trip, which drops the build metadata that
            distinguishes film from substrate.
    """
    if substrate_elements is None:
        film = _cartesian_coordinates(interface_get_part(interface, part=InterfacePartsEnum.FILM))
        substrate = _cartesian_coordinates(interface_get_part(interface, part=InterfacePartsEnum.SUBSTRATE))
    else:
        coordinates = _cartesian_coordinates(interface)
        is_substrate = np.array([e in substrate_elements for e in interface.basis.elements.values])
        film, substrate = coordinates[~is_substrate], coordinates[is_substrate]
    top_layer = substrate[substrate[:, 2] > substrate[:, 2].max() - LAYER_TOLERANCE]
    return float(film[:, 2].mean() - top_layer[:, 2].mean())


def get_film_and_substrate(interface: Material) -> Tuple[Material, Material]:
    """The film and substrate as separate materials, keeping the interface cell."""
    return (
        interface_get_part(interface, part=InterfacePartsEnum.FILM),
        interface_get_part(interface, part=InterfacePartsEnum.SUBSTRATE),
    )
