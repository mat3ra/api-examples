from typing import List

import numpy as np
from mat3ra.made.material import Material
from mat3ra.made.tools.convert import to_ase

EV_PER_ANGSTROM2_TO_J_PER_M2 = 16.0217663


def get_in_plane_area(material: Material) -> float:
    """Area of the cell's in-plane face, in Angstrom^2."""
    vectors = np.array(material.lattice.vector_arrays)
    return float(np.linalg.norm(np.cross(vectors[0], vectors[1])))


def get_work_of_adhesion(combined_energy: float, part_energies: List[float], material: Material) -> float:
    """
    Work of adhesion in J/m^2: the energy released when the separated parts are brought together,
    per unit interface area. Positive means bound.

    The part energies must come from calculations in the same cell and with the same settings as
    the combined one, so that basis- and sampling-dependent errors cancel in the difference.

    Args:
        combined_energy: Total energy of the assembled structure, eV.
        part_energies: Total energies of the separated parts, eV.
        material: Any structure sharing the interface cell, read for its in-plane area.
    """
    released = sum(part_energies) - combined_energy
    return released / get_in_plane_area(material) * EV_PER_ANGSTROM2_TO_J_PER_M2


def get_energy(material: Material, calculator) -> float:
    """Total energy of a material from an ASE calculator, in eV."""
    atoms = to_ase(material)
    atoms.calc = calculator
    return float(atoms.get_potential_energy())
