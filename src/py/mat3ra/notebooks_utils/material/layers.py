from typing import List, Optional

import numpy as np
from mat3ra.made.material import Material


def get_atom_indices_by_layer(material: Material, tolerance: float = 0.5) -> List[List[int]]:
    """
    Atom indices grouped into layers along z, bottom layer first. Consecutive heights closer than
    `tolerance` Angstrom belong to one layer, so the grouping does not depend on basis order.
    """
    cartesian = material.clone()
    cartesian.to_cartesian()
    heights = np.array(cartesian.coordinates_array)[:, 2]
    layers: List[List[int]] = []
    previous: Optional[float] = None
    for index in np.argsort(heights, kind="stable"):
        if previous is None or heights[index] - previous > tolerance:
            layers.append([])
        layers[-1].append(int(index))
        previous = float(heights[index])
    return layers


def get_atom_indices_in_bottom_layers(
    material: Material, layer_count: int, atom_indices: Optional[List[int]] = None, tolerance: float = 0.5
) -> List[int]:
    """
    Indices of the atoms in the `layer_count` lowest layers, restricted to `atom_indices` when
    given — e.g. the substrate's, to hold its deepest layers fixed during a relaxation.
    """
    if layer_count < 1:
        raise ValueError("layer_count must be at least 1")
    selected = None if atom_indices is None else set(atom_indices)
    layers = [
        [index for index in layer if selected is None or index in selected]
        for layer in get_atom_indices_by_layer(material, tolerance)
    ]
    occupied = [layer for layer in layers if layer]
    return sorted(index for layer in occupied[:layer_count] for index in layer)
