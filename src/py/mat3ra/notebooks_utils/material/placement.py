from itertools import product
from typing import Dict, List, Optional, Sequence

import numpy as np
from mat3ra.made.material import Material
from mat3ra.made.tools.analyze.other import get_closest_site_id_from_coordinate_and_element
from mat3ra.made.tools.convert.interface_parts_enum import InterfacePartsEnum
from mat3ra.made.tools.modify import interface_displace_part

from .surface_sites import SurfaceSiteAnalyzer

NEIGHBOUR_STRETCH = 1.3  # atoms further apart than this times the closest pair are not one site


def get_atom_indices(material: Material, element: Optional[str] = None) -> List[int]:
    """Indices of the atoms of `element` (all atoms when None), in basis order."""
    return [i for i, e in enumerate(material.basis.elements.values) if element is None or e == element]


def get_atom_index(
    material: Material, element: str, near: Sequence[float], use_cartesian_coordinates: bool = False
) -> int:
    """
    The index of the `element` atom closest to `near` — the way a human points at an atom:
    "the Mo near (0.25, 0.25, 0.5)". Coordinates are crystal unless `use_cartesian_coordinates`.
    """
    return int(
        get_closest_site_id_from_coordinate_and_element(material, list(near), element, use_cartesian_coordinates)
    )


def describe_atoms(material: Material, indices: Optional[Sequence[int]] = None) -> List[Dict]:
    """Index, element and crystal coordinate of each atom, for checking a choice before using it."""
    crystal = material.clone()
    crystal.to_crystal()
    chosen = range(len(crystal.basis.elements.values)) if indices is None else indices
    return [
        {
            "index": int(i),
            "element": crystal.basis.elements.values[i],
            "coordinate": [round(x, 4) for x in crystal.coordinates_array[i]],
        }
        for i in chosen
    ]


def _cartesian_xy(material: Material) -> np.ndarray:
    cartesian = material.clone()
    cartesian.to_cartesian()
    return np.array(cartesian.coordinates_array)[:, :2]


def _periodic_shifts(vectors_2d: np.ndarray) -> np.ndarray:
    return np.array([i * vectors_2d[0] + j * vectors_2d[1] for i in (-1, 0, 1) for j in (-1, 0, 1)])


def _nearest_image(point_xy: np.ndarray, reference_xy: np.ndarray, vectors_2d: np.ndarray) -> np.ndarray:
    """The periodic image of a point closest to the reference."""
    images = point_xy + _periodic_shifts(vectors_2d)
    return images[np.argmin(np.linalg.norm(images - reference_xy, axis=1))]


def _compact_images(points_xy: np.ndarray, vectors_2d: np.ndarray) -> np.ndarray:
    """One periodic image per point, chosen so the set is as tight as possible — the images that
    together form a site, not the ones that each happen to be nearest to the first atom."""
    if len(points_xy) == 1:
        return points_xy
    shifts = _periodic_shifts(vectors_2d)
    best, best_spread = None, np.inf
    for choice in product(range(len(shifts)), repeat=len(points_xy) - 1):
        images = np.vstack([points_xy[0], points_xy[1:] + shifts[list(choice)]])
        spread = max(np.linalg.norm(a - b) for k, a in enumerate(images) for b in images[k + 1 :])
        if spread < best_spread:
            best, best_spread = images, spread
    return best if best is not None else points_xy


def _nearest_neighbour_distance(material: Material, atom: int, vectors_2d: np.ndarray) -> float:
    """In-plane distance from `atom` to the closest other atom of its own layer, images included."""
    cartesian = material.clone()
    cartesian.to_cartesian()
    pos = np.array(cartesian.coordinates_array)
    same_layer = [i for i in range(len(pos)) if i != atom and abs(pos[i, 2] - pos[atom, 2]) < 0.5]
    shifts = _periodic_shifts(vectors_2d)
    return float(min(np.linalg.norm(pos[i, :2] + s - pos[atom, :2]) for i in same_layer for s in shifts))


def place_over(interface: Material, film_atom: int, substrate_atoms: Sequence[int]) -> Material:
    """
    Translate the film so that one film atom sits over one substrate atom (atop), the midpoint of
    two (bridge) or the centre of three (hollow). Indices are the interface's own, as a viewer shows
    them. The rest of the film follows rigidly; nothing rotates.

    Raises:
        ValueError: when the indices are not film / substrate atoms, or the chosen substrate atoms
            are not neighbours of one another (their centre would not be a site).
    """
    labels = interface.basis.labels.values
    if labels[film_atom] != InterfacePartsEnum.FILM.value:
        raise ValueError(f"Atom {film_atom} is not in the film")
    if any(labels[i] != InterfacePartsEnum.SUBSTRATE.value for i in substrate_atoms):
        raise ValueError(f"Not all of {list(substrate_atoms)} are substrate atoms")
    xy = _cartesian_xy(interface)
    vectors_2d = np.array(interface.lattice.vector_arrays)[:2, :2]
    chosen = _compact_images(xy[list(substrate_atoms)], vectors_2d)
    if len(chosen) > 1:
        gaps = [np.linalg.norm(a - b) for k, a in enumerate(chosen) for b in chosen[k + 1 :]]
        nearest = _nearest_neighbour_distance(interface, substrate_atoms[0], vectors_2d)
        if max(gaps) > NEIGHBOUR_STRETCH * nearest or min(gaps) < 1e-6:
            distances = ", ".join(f"{gap:.2f}" for gap in gaps)
            raise ValueError(f"Substrate atoms {list(substrate_atoms)} are not one site's neighbours ({distances} A)")
    target = chosen.mean(axis=0)
    shift = target - _nearest_image(xy[film_atom], target, vectors_2d)
    return interface_displace_part(interface, displacement=[float(shift[0]), float(shift[1]), 0.0])


def get_film_site_occupation(
    interface: Material, analyzer: Optional[SurfaceSiteAnalyzer] = None
) -> Dict[int, Optional[str]]:
    """Which named substrate site each film atom sits on (None: no site) — index -> name."""
    if analyzer is None:
        substrate = interface.clone()
        substrate.basis.filter_atoms_by_labels([InterfacePartsEnum.SUBSTRATE.value])
        analyzer = SurfaceSiteAnalyzer(substrate)
    xy = _cartesian_xy(interface)
    return {
        i: analyzer.get_site_name(xy[i])
        for i in get_atom_indices(interface)
        if interface.basis.labels.values[i] == InterfacePartsEnum.FILM.value
    }
