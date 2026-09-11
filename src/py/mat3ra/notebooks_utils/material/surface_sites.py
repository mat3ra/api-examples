from enum import Enum
from functools import cached_property
from typing import Dict, List, Optional, Union

import numpy as np
from mat3ra.made.material import Material
from scipy.spatial import Voronoi, cKDTree

from .layers import get_atom_indices_by_layer

PERIODIC_SHIFTS = [(i, j) for i in (-1, 0, 1) for j in (-1, 0, 1)]
FRACTIONAL_DECIMALS = 4


class SurfaceSiteEnum(str, Enum):
    ATOP = "atop"
    BRIDGE = "bridge"
    FCC = "fcc"
    HCP = "hcp"
    HOLLOW = "hollow"


def _tile(points_xy: np.ndarray, vectors_2d: np.ndarray) -> np.ndarray:
    """The 3x3 periodic images, home cell included, so sites across a cell boundary are seen."""
    return np.vstack([points_xy + i * vectors_2d[0] + j * vectors_2d[1] for i, j in PERIODIC_SHIFTS])


class SurfaceSiteAnalyzer:
    """
    High-symmetry adsorption sites of a slab's top surface, as cartesian in-plane coordinates.

    Sites come from the surface layer's geometry alone: "atop" over a surface atom, "bridge" at the
    midpoint of two natural-neighbour surface atoms, and hollows at the points equidistant from
    three or more surface atoms (the Voronoi vertices of the surface net). A three-fold hollow is
    "hcp" when an atom of the second layer lies beneath it and "fcc" when one of the third layer
    does; any other hollow — a four-fold hollow, or an hcp(0001) hollow over an empty column — is
    "hollow". Any lattice and Miller index whose surface is flat within `layer_tolerance` works.

    Tolerances, in Angstrom: `layer_tolerance` separates layers (interlayer spacings exceed 1.5 in
    metals; 0.5 absorbs relaxation buckling); `site_match_tolerance` is how close a point must be to
    count as on a site, and how close a subsurface atom must be to name a hollow; `tie_tolerance` is
    the distance difference below which two site types count as equally close.
    """

    def __init__(
        self,
        material: Material,
        layer_tolerance: float = 0.5,
        site_match_tolerance: float = 0.3,
        tie_tolerance: float = 0.05,
    ):
        self.material = material
        self.layer_tolerance = layer_tolerance
        self.site_match_tolerance = site_match_tolerance
        self.tie_tolerance = tie_tolerance

    @cached_property
    def in_plane_vectors(self) -> np.ndarray:
        return np.array(self.material.lattice.vector_arrays)[:2, :2]

    @cached_property
    def layers_xy(self) -> List[np.ndarray]:
        """In-plane coordinates of each layer, top surface first."""
        cartesian = self.material.clone()
        cartesian.to_cartesian()
        coordinates = np.array(cartesian.coordinates_array)
        layers = get_atom_indices_by_layer(self.material, self.layer_tolerance)
        return [self._wrap_points(coordinates[indices][:, :2]) for indices in reversed(layers)]

    @cached_property
    def sites(self) -> Dict[str, List[List[float]]]:
        """Site name -> every instance of that site in the cell, as [x, y] in Angstrom."""
        surface_xy = self.layers_xy[0]
        sites = {
            SurfaceSiteEnum.ATOP.value: self._wrap_into_cell(surface_xy).tolist(),
            SurfaceSiteEnum.BRIDGE.value: self._bridges().tolist(),
        }
        for name, points in self._hollows().items():
            sites[name] = np.array(points).tolist()
        return sites

    def _fractional(self, points_xy: np.ndarray) -> np.ndarray:
        return np.round(points_xy @ np.linalg.inv(self.in_plane_vectors), FRACTIONAL_DECIMALS)

    def _wrap_points(self, points_xy: np.ndarray) -> np.ndarray:
        """Points mapped into the home cell, so the periodic tiling is always centred on it."""
        return (np.mod(self._fractional(points_xy), 1.0) % 1.0) @ self.in_plane_vectors

    def _wrap_into_cell(self, points_xy: np.ndarray) -> np.ndarray:
        """Lattice-periodic points (atoms) mapped into the home cell, one instance each."""
        fractional = np.mod(self._fractional(points_xy), 1.0)
        return np.unique(np.round(fractional, FRACTIONAL_DECIMALS) % 1.0, axis=0) @ self.in_plane_vectors

    def _inside_home_cell(self, points_xy: np.ndarray) -> np.ndarray:
        """Derived points (from the 3x3 tiling) that fall in the home cell, one instance each."""
        fractional = self._fractional(points_xy)
        inside = np.all((fractional >= 0.0) & (fractional < 1.0), axis=1)
        return np.unique(fractional[inside], axis=0) @ self.in_plane_vectors

    @cached_property
    def _surface_voronoi(self) -> Voronoi:
        return Voronoi(_tile(self.layers_xy[0], self.in_plane_vectors))

    def _bridges(self) -> np.ndarray:
        """Midpoints of natural-neighbour pairs: atoms whose Voronoi cells share a ridge of real
        length (a square net's degenerate diagonal is not a bond)."""
        voronoi = self._surface_voronoi
        midpoints = []
        for (a, b), ridge in zip(voronoi.ridge_points, voronoi.ridge_vertices):
            degenerate = (
                -1 in ridge or np.linalg.norm(np.diff(voronoi.vertices[ridge], axis=0)) < self.site_match_tolerance
            )
            if degenerate:
                continue
            midpoints.append((voronoi.points[a] + voronoi.points[b]) / 2)
        return self._inside_home_cell(np.array(midpoints))

    def _hollows(self) -> Dict[str, List[np.ndarray]]:
        tiled = self._surface_voronoi.points
        hollows: Dict[str, List[np.ndarray]] = {}
        for vertex in self._inside_home_cell(self._surface_voronoi.vertices):
            distances = np.linalg.norm(tiled - vertex, axis=1)
            coordination = int(np.sum(distances < distances.min() + self.site_match_tolerance))
            hollows.setdefault(self._hollow_name(vertex, coordination), []).append(vertex)
        return hollows

    def _hollow_name(self, hollow_xy: np.ndarray, coordination: int) -> str:
        if coordination != 3:
            return SurfaceSiteEnum.HOLLOW.value
        for name, depth in ((SurfaceSiteEnum.HCP.value, 1), (SurfaceSiteEnum.FCC.value, 2)):
            if (
                depth < len(self.layers_xy)
                and self._distance_to_points(hollow_xy, self.layers_xy[depth]) < self.site_match_tolerance
            ):
                return name
        return SurfaceSiteEnum.HOLLOW.value

    def _distance_to_points(self, coordinate_xy: np.ndarray, points_xy: np.ndarray) -> float:
        """Distance to the nearest periodic image of any of the points."""
        return float(cKDTree(_tile(points_xy, self.in_plane_vectors)).query(coordinate_xy)[0])

    def get_site_name(self, coordinate_xy: List[float]) -> Optional[str]:
        """
        The site a point sits on, within `site_match_tolerance`; None when it is on no site or two
        site types are equally close — an ambiguous label is how an adsorbed structure gets reported
        under the wrong registry.
        """
        point = np.array(coordinate_xy[:2], dtype=float)
        distances = {name: self._distance_to_points(point, np.array(points)) for name, points in self.sites.items()}
        ranked = sorted(distances, key=lambda name: distances[name])
        if distances[ranked[0]] > self.site_match_tolerance:
            return None
        if len(ranked) > 1 and distances[ranked[1]] - distances[ranked[0]] < self.tie_tolerance:
            return None
        return ranked[0]

    def get_displacement_to_site(
        self, coordinate_xy: List[float], site_name: Union[str, SurfaceSiteEnum]
    ) -> List[float]:
        """The in-plane shift, as a 3D vector, that moves a point onto the nearest instance of a site."""
        name = SurfaceSiteEnum(site_name).value
        if name not in self.sites:
            raise ValueError(f"No '{name}' site on this surface; present: {sorted(self.sites)}")
        point = np.array(coordinate_xy[:2], dtype=float)
        images = _tile(np.array(self.sites[name]), self.in_plane_vectors)
        nearest = images[np.argmin(np.linalg.norm(images - point, axis=1))]
        return [float(nearest[0] - point[0]), float(nearest[1] - point[1]), 0.0]
