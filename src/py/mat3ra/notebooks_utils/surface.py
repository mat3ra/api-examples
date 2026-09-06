from typing import Dict, List, Optional

import numpy as np
from mat3ra.made.material import Material
from scipy.spatial import Delaunay

DEFAULT_LAYER_TOLERANCE = 0.5  # Angstrom; atoms within this of each other count as one layer
SITE_MATCH_TOLERANCE = 0.3  # Angstrom; how close a subsurface atom must be to sit "under" a hollow


def _layers(material: Material, tolerance: float) -> List[np.ndarray]:
    """Cartesian coordinates grouped into layers, surface first."""
    cartesian = material.clone()
    cartesian.to_cartesian()
    coordinates = np.array(cartesian.basis.coordinates.values)
    layers: List[np.ndarray] = []
    for z in sorted(coordinates[:, 2], reverse=True):
        if any(abs(z - group[0][2]) < tolerance for group in layers):
            continue
        layers.append(coordinates[np.abs(coordinates[:, 2] - z) < tolerance])
    return layers


def _tiled(points_xy: np.ndarray, vectors_2d: np.ndarray) -> np.ndarray:
    """The 3x3 periodic tiling, so sites on and across the cell boundary are found alike."""
    shifts = [i * vectors_2d[0] + j * vectors_2d[1] for i in (-1, 0, 1) for j in (-1, 0, 1)]
    return np.vstack([points_xy + shift for shift in shifts])


def _hollow_name(hollow_xy: np.ndarray, layers: List[np.ndarray], vectors_2d: np.ndarray) -> str:
    """A three-fold hollow is 'hcp' when the second layer sits under it, 'fcc' when the third does."""
    for name, depth in (("hcp", 1), ("fcc", 2)):
        if depth >= len(layers):
            continue
        distances = np.linalg.norm(_tiled(layers[depth][:, :2], vectors_2d) - hollow_xy, axis=1)
        if distances.min() < SITE_MATCH_TOLERANCE:
            return name
    return "hollow"


def get_surface_sites(material: Material, layer_tolerance: float = DEFAULT_LAYER_TOLERANCE) -> Dict[str, np.ndarray]:
    """
    High-symmetry adsorption sites on the top surface, as in-plane cartesian coordinates.

    Keys are the conventional names: "atop" (over a surface atom), "bridge" (between two of them),
    and the hollows — "fcc" and "hcp" where a three-fold hollow can be told apart by which
    subsurface layer lies beneath it, otherwise "hollow". Works for any lattice and Miller index
    whose surface layer is flat within `layer_tolerance`.

    Args:
        material: A slab or interface; only its topmost substrate layers are read.
        layer_tolerance: Height spread within which atoms count as one layer, in Angstrom.

    Returns:
        Site name -> [x, y] in Angstrom. Absent site types are omitted.
    """
    layers = _layers(material, layer_tolerance)
    vectors_2d = np.array(material.lattice.vector_arrays)[:2, :2]
    surface = layers[0][:, :2]
    tiled = _tiled(surface, vectors_2d)
    sites = {"atop": surface[0]}

    triangles = Delaunay(tiled).simplices
    centroids = [tiled[corners].mean(axis=0) for corners in triangles]
    midpoints = [tiled[list(pair)].mean(axis=0) for corners in triangles for pair in _edges(corners)]

    for points, fixed_name in ((midpoints, "bridge"), (centroids, None)):
        for point in sorted(points, key=lambda p: np.linalg.norm(p - sites["atop"])):
            sites.setdefault(fixed_name or _hollow_name(point, layers, vectors_2d), point)
    return sites


def _edges(triangle_corners) -> List[tuple]:
    a, b, c = triangle_corners
    return [(a, b), (b, c), (a, c)]


def get_site_displacement(material: Material, atom_index: int, site: np.ndarray) -> List[float]:
    """
    The in-plane shift that puts one atom of `material` onto `site`, as a 3D vector.

    Applied to a whole film (see `interface_displace_part`) it moves the film into the registry
    where that atom occupies the named site, leaving the film's internal geometry untouched.
    """
    cartesian = material.clone()
    cartesian.to_cartesian()
    position = np.array(cartesian.basis.coordinates.values[atom_index])
    return [float(site[0] - position[0]), float(site[1] - position[1]), 0.0]


def get_site_of(
    material: Material, position_xy: np.ndarray, sites: Optional[Dict[str, np.ndarray]] = None
) -> Optional[str]:
    """
    Which named site a position sits on, or None when two sites are equally close.

    Returning None rather than guessing matters for registry comparisons: an ambiguous label is
    how a structure ends up reported under the wrong name.
    """
    sites = sites if sites is not None else get_surface_sites(material)
    vectors_2d = np.array(material.lattice.vector_arrays)[:2, :2]
    distances = {
        name: np.linalg.norm(_tiled(np.array([site]), vectors_2d) - position_xy, axis=1).min()
        for name, site in sites.items()
    }
    nearest, runner_up = sorted(distances.values())[:2] if len(distances) > 1 else (0.0, 1.0)
    return None if runner_up - nearest < 0.05 else min(distances, key=lambda name: distances[name])
