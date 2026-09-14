from typing import Optional, Sequence

from ase.constraints import FixAtoms, FixedLine
from ase.optimize import BFGS
from mat3ra.made.material import Material
from mat3ra.made.tools.convert import to_ase
from mat3ra.made.tools.third_party import ASECalculator

Z_DIRECTION = [0, 0, 1]


def relax_material(
    material: Material,
    calculator: ASECalculator,
    fmax: float = 0.05,
    max_steps: int = 300,
    fixed_atom_indices: Optional[Sequence[int]] = None,
    along_z_only: bool = False,
    logfile: Optional[str] = "-",
) -> Material:
    """
    Relax atomic positions with an ASE calculator (e.g. from `create_mlff_calculator`) at fixed
    cell, optionally holding atoms fixed or allowing motion along z only.

    Args:
        material: The structure to relax; labels and build metadata are preserved in the result.
        calculator: Any ASE calculator.
        fmax: Force convergence criterion, eV/Angstrom.
        max_steps: Optimizer step limit.
        fixed_atom_indices: Atoms held fixed.
        along_z_only: Restrict every atom's motion to the z direction.
        logfile: ASE optimizer log target; "-" is stdout, None silences it.

    Raises:
        RuntimeError: when the optimizer stops before the forces fall below `fmax`.
    """
    atoms = to_ase(material)
    constraints = []
    if fixed_atom_indices:
        constraints.append(FixAtoms(indices=list(fixed_atom_indices)))
    if along_z_only:
        constraints.append(FixedLine(list(range(len(atoms))), direction=Z_DIRECTION))
    if constraints:
        atoms.set_constraint(constraints)
    atoms.calc = calculator
    converged = BFGS(atoms, logfile=logfile).run(fmax=fmax, steps=max_steps)
    if not converged:
        raise RuntimeError(f"Relaxation of '{material.name}' did not reach fmax={fmax} eV/A within {max_steps} steps.")

    relaxed = material.clone()
    was_in_crystal_units = relaxed.basis.is_in_crystal_units
    relaxed.to_cartesian()
    relaxed.set_coordinates(atoms.positions.tolist())
    if was_in_crystal_units:
        relaxed.to_crystal()
    return relaxed
