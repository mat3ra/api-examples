from typing import Sequence, Union

import numpy as np
from mat3ra.made.material import Material


def translate_atoms(
    material: Material,
    atom_indices: Union[int, Sequence[int]],
    vector: Sequence[float],
    use_cartesian_coordinates: bool = True,
) -> Material:
    """
    Move selected atoms by a vector, leaving every other atom where it was.

    Args:
        material (Material): Material to modify. Not mutated; a clone is returned.
        atom_indices (int | Sequence[int]): Index or indices of the atoms to move.
        vector (Sequence[float]): Displacement, in Angstrom when
            `use_cartesian_coordinates` (default) else in crystal coordinates.
        use_cartesian_coordinates (bool): Interpret `vector` as Angstrom.

    Returns:
        Material: A new material with the selected atoms displaced.

    Raises:
        IndexError: If any index is out of range for the basis.
    """
    if isinstance(atom_indices, int):
        atom_indices = [atom_indices]

    coordinates = [list(coordinate) for coordinate in material.coordinates_array]
    out_of_range = [index for index in atom_indices if not -len(coordinates) <= index < len(coordinates)]
    if out_of_range:
        raise IndexError(f"Atom indices {out_of_range} are out of range for a basis of {len(coordinates)} atoms.")

    if use_cartesian_coordinates:
        inverse_lattice_vectors = np.linalg.inv(np.array(material.lattice.vector_arrays))
        vector = (np.array(vector) @ inverse_lattice_vectors).tolist()

    moved_material = material.clone()
    for index in atom_indices:
        coordinates[index] = [value + delta for value, delta in zip(coordinates[index], vector)]
    moved_material.set_coordinates(coordinates)
    return moved_material
