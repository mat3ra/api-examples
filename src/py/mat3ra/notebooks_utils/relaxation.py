from typing import List, Optional

from ase.constraints import FixAtoms, FixCartesian
from ase.optimize import BFGS
from mat3ra.made.material import Material
from mat3ra.made.tools.convert import from_ase, to_ase

DEFAULT_FMAX = 0.05  # eV/Angstrom, the usual force convergence for a surface relaxation


def _frozen_indices(atoms, elements: Optional[List[str]], layer_count: int) -> List[int]:
    """Indices of the `layer_count` deepest atoms, optionally restricted to given elements."""
    candidates = [
        index for index, symbol in enumerate(atoms.get_chemical_symbols()) if elements is None or symbol in elements
    ]
    heights = sorted({round(atoms.positions[i, 2], 1) for i in candidates})[:layer_count]
    return [i for i in candidates if round(atoms.positions[i, 2], 1) in heights]


def relax(
    material: Material,
    calculator,
    fmax: float = DEFAULT_FMAX,
    max_steps: int = 300,
    frozen_layer_count: int = 0,
    frozen_elements: Optional[List[str]] = None,
    in_plane_fixed: bool = False,
) -> Material:
    """
    Relax a material with a machine-learned force field, holding part of it fixed.

    The usual surface recipe is to freeze the deepest substrate layers so they stand in for bulk,
    which is what published slab calculations do. `in_plane_fixed` additionally allows motion along
    z only — useful when a structure must keep its registry, since an unconstrained relaxation can
    slide a film into a neighbouring one.

    Args:
        material: The structure to relax.
        calculator: An ASE calculator, e.g. from `create_mlff_calculator`.
        fmax: Force convergence criterion, eV/Angstrom.
        max_steps: Optimizer step limit.
        frozen_layer_count: How many of the deepest layers to hold fixed.
        frozen_elements: Restrict freezing to these elements, e.g. the substrate's.
        in_plane_fixed: Allow motion along z only.

    Returns:
        The relaxed material.
    """
    atoms = to_ase(material)
    constraints = []
    if in_plane_fixed:
        constraints.append(FixCartesian(list(range(len(atoms))), mask=(True, True, False)))
    if frozen_layer_count:
        constraints.append(FixAtoms(indices=_frozen_indices(atoms, frozen_elements, frozen_layer_count)))
    if constraints:
        atoms.set_constraint(constraints)
    atoms.calc = calculator
    BFGS(atoms).run(fmax=fmax, steps=max_steps)
    relaxed = Material.create(from_ase(atoms))
    relaxed.name = material.name
    # The ASE round-trip keeps only positions and species; build metadata says what the structure
    # IS, which relaxation does not change, so carrying it over keeps helpers like
    # `interface_get_part` working on a relaxed structure.
    try:
        relaxed.metadata = material.metadata
    except (AttributeError, ValueError, TypeError):
        pass
    return relaxed
