from typing import Any, Dict, Tuple, Union

import ase.build
import ase.constraints
import numpy as np
import pymatgen.core.surface
import pymatgen.io.ase
import pymatgen.symmetry.analyzer
from mat3ra.made.material import Material
from mat3ra.made.tools.analyze.slab import SlabMaterialAnalyzer
from mat3ra.made.tools.build import MaterialWithBuildMetadata


def is_symmetric(slab: pymatgen.core.structure.Structure) -> bool:
    """
    Checks whether a slab is in a point group with inversion symmetry.

    Args:
        slab (pymatgen.core.structure.Structure): Slab of interest

    Returns:
        True if the slab's spacegroup has inversion symmetry, otherwise False.
    """
    spacegroup = pymatgen.symmetry.analyzer.SpacegroupAnalyzer(slab)
    return spacegroup.is_laue()


def get_all_slabs_and_terms(
    crystal: pymatgen.core.structure.Structure, thickness: Union[int, float], is_by_layers: bool
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Gets all slabs and terminations for a given crystal.

    Args:
        crystal (pymatgen.core.structure.Structure): Crystal of interest
        thickness (int or float): How thick the slab should be
        is_by_layers (bool): Whether thickness is by number of layers or angstroms

    Returns:
        Dict
    """
    all_indices = pymatgen.core.surface.get_symmetrically_distinct_miller_indices(crystal, max_index=3)
    slabs = {}

    for plane in all_indices:
        slab_generator = pymatgen.core.surface.SlabGenerator(
            crystal, plane, min_slab_size=thickness, min_vacuum_size=10, center_slab=True, in_unit_planes=is_by_layers
        )
        all_terminations = slab_generator.get_slabs()
        term_dict = {}
        symmetric_terminations = filter(is_symmetric, all_terminations)
        for term, surface in enumerate(symmetric_terminations):
            ase_surface = pymatgen.io.ase.AseAtomsAdaptor.get_atoms(surface)
            term_dict[str(term)] = {"slab": ase_surface}
        slabs["".join(map(str, plane))] = term_dict
    return slabs


def get_bulk_bottom_and_top_frac_coords(slab: ase.Atoms, layers: int = 3) -> Tuple[float, float]:
    """
    Finds the top and bottom of the bulk, in fractional coordinates.

    Args:
        slab (ase.Atoms): The slab of interest
        layers (int): How many layers are in the slab

    Returns:
        Tuple of (bulk_bottom, bulk_top) fractional coordinates.
    """
    c_direction_coords = [atom.scaled_position[2] for atom in slab]
    slab_range = max(c_direction_coords) - min(c_direction_coords)
    layer_size = slab_range / layers
    bulk_bottom = min(c_direction_coords) + layer_size
    bulk_top = min(c_direction_coords) + 2 * layer_size
    return (bulk_bottom, bulk_top)


def freeze_center_bulk(slab: ase.Atoms) -> None:
    """
    Applies an ASE FixAtoms constraint to atoms found in the center of the slab, in-place.

    Args:
        slab (ase.Atoms): The slab of interest
    """
    bulk_bottom, bulk_top = get_bulk_bottom_and_top_frac_coords(slab)
    frozen_atoms = filter(lambda atom: bulk_bottom <= atom.scaled_position[2] <= bulk_top, slab)
    frozen_atoms_indices = [atom.index for atom in frozen_atoms]
    fix_atoms_constraint = ase.constraints.FixAtoms(indices=frozen_atoms_indices)
    slab.set_constraint(fix_atoms_constraint)


def get_surface_energy(e_slab: float, e_bulk: float, n_slab: float, n_bulk: float, a: float) -> float:
    """
    Calculates the slab surface energy:
    (E_Slab - E_bulk * (N_Slab / N_Bulk)) / (2A)
    """
    return (e_slab - e_bulk * (n_slab / n_bulk)) / (2 * a)


def get_slab_area(a_vector: np.ndarray, b_vector: np.ndarray) -> float:
    """
    Gets the area of a slab defined by the two unit vectors.

    Args:
        a_vector: First lattice vector.
        b_vector: Second lattice vector.
    """
    crossprod = np.cross(a_vector, b_vector)
    return np.linalg.norm(crossprod)


def get_slab_bulk_crystal(slab_material: Material) -> dict:
    """Gets the bulk crystal a slab was built from, as recorded in its build metadata."""
    slab_with_metadata = MaterialWithBuildMetadata.create(slab_material.to_dict())
    crystal = SlabMaterialAnalyzer(material=slab_with_metadata).build_configuration.atomic_layers.crystal
    if crystal is None:
        raise ValueError("No bulk crystal for slab in build metadata.")
    return crystal if isinstance(crystal, dict) else crystal.to_dict()


def resolve_bulk_query_from_crystal(bulk_crystal: dict) -> dict:
    """Builds a materials.list query that resolves a bulk crystal to a platform material."""
    for key in ("scaledHash", "hash", "_id"):
        if bulk_crystal.get(key) is not None:
            return {key: bulk_crystal[key]}
    try:
        return {"hash": Material.create(bulk_crystal).hash}
    except Exception as exc:
        raise ValueError("Could not resolve a bulk query from crystal metadata.") from exc
