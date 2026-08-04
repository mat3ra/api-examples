from typing import List, Sequence, Union

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

    Made's translate operations move the whole material and its perturbation
    functions apply to every atom, so displacing a single site — an adatom
    hop, a vacancy relaxation, one end of a reaction path — has no helper.

    Args:
        material (Material): Material to modify. Not mutated; a clone is returned.
        atom_indices (int | Sequence[int]): Index or indices of the atoms to move.
        vector (Sequence[float]): Displacement, in Angstrom when
            `use_cartesian_coordinates` (default) else in crystal coordinates.
        use_cartesian_coordinates (bool): Interpret `vector` as Angstrom. Prefer
            this — a crystal delta means a different distance in every cell.

    Returns:
        Material: A new material with the selected atoms displaced.

    Raises:
        IndexError: If any index is out of range for the basis.

    Note:
        Coordinates are not wrapped back into the cell, so an atom may end up
        outside it — legal under periodic boundary conditions, but harder to
        read. Displace away from the cell edge when the images are for a human.
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


def get_atom_indices_by_height(material: Material, count: int = 1, from_top: bool = True) -> List[int]:
    """
    Indices of the `count` highest (or lowest) atoms along the third lattice vector.

    Picking a surface atom by eye means hardcoding an index that silently points
    at a different atom as soon as the slab changes.

    Args:
        material (Material): Material to inspect.
        count (int): How many atoms to return.
        from_top (bool): Return the highest atoms; otherwise the lowest.

    Returns:
        list[int]: Atom indices, ordered outermost first.
    """
    heights = [coordinate[2] for coordinate in material.coordinates_array]
    ordered = sorted(range(len(heights)), key=lambda index: heights[index], reverse=from_top)
    return ordered[:count]
