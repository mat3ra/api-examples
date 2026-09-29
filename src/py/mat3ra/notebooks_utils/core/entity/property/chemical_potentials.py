from typing import Dict, Tuple

import numpy as np


def solve_chemical_potentials(reference_energies: Dict[str, Tuple[Dict[str, int], float]]) -> Dict[str, float]:
    """
    Chemical potential of each element (eV/atom) from one reference material per element, given as its atom counts
    and its total energy (eV) for them: each material gives E = sum_i n_i * mu_i, and the square system is solved.

    Raises:
        ValueError: If the materials contain other elements than the keys, or do not determine every potential.
    """
    elements = sorted(reference_energies)
    compositions = [composition for composition, _ in reference_energies.values()]
    if set().union(*compositions) != set(elements):
        raise ValueError(f"The reference materials must contain exactly the elements {elements}.")
    matrix = np.array([[composition.get(element, 0) for element in elements] for composition in compositions])
    if np.linalg.matrix_rank(matrix) < len(elements):
        raise ValueError("The reference materials do not determine every chemical potential.")
    energies = [energy for _, energy in reference_energies.values()]
    return dict(zip(elements, np.linalg.solve(matrix, energies).tolist()))
