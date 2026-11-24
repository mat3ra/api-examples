# ---------------------------------------------------------------- #
#                                                                  #
#  Step 2, "Relax under AFIR Force (ALCHEMI)", of the workflow     #
#  "Molecule on Surface: AFIR Search (ALCHEMI)", with MACE through #
#  NVIDIA ALCHEMI on one GPU.                                      #
#                                                                  #
#  Relaxes the configurations in batches of BATCH_SIZE with the    #
#  slab fixed, first under an artificial force between molecule    #
#  and slab, as in the artificial force induced reaction (AFIR)    #
#  method (GRRM17 Eqs. 1-3 [1], strength GAMMA), then without it,  #
#  and ranks the final structures by energy.                       #
#                                                                  #
#  Reads:  configurations.extxyz, written by "Create Initial       #
#          Configurations" in the job's work folder; slab atoms    #
#          tagged 0, molecule atoms 1.                             #
#  Writes: ranked_configurations.csv, every configuration ranked   #
#          by final energy, with its starting rotation and         #
#          position and the number of fragments its molecule ends  #
#          in; final_structures.extxyz, the                        #
#          NUMBER_OF_FINAL_STRUCTURES lowest in that order; and    #
#          final_energies.png, final energy against configuration  #
#          index. ranked_configurations.csv and final_energies.png #
#          are results of this unit.                               #
#                                                                  #
#  [1] S. Maeda et al., J. Comput. Chem. 39, 233 (2018).           #
#                                                                  #
# ---------------------------------------------------------------- #

import csv
from importlib.metadata import version

import matplotlib
import numpy as np
import torch
from ase.build import separate
from ase.calculators.singlepoint import SinglePointCalculator
from ase.data import covalent_radii
from ase.io import read, write
from ase.units import kJ, mol
from loguru import logger
from nvalchemi._typing import AtomCategory
from nvalchemi.data import AtomicData, Batch
from nvalchemi.dynamics import FIRE2, FusedStage
from nvalchemi.dynamics.base import ConvergenceHook, DynamicsStage
from nvalchemi.dynamics.hooks import FreezeAtomsHook
from nvalchemi.hooks import BiasedPotentialHook
from nvalchemi.models.mace import MACEWrapper

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEVICE = "cuda:0"
CHECKPOINT = "medium-mpa-0"  # MACE-MPA-0, medium
DTYPE = torch.float32
FMAX = 0.03  # eV/Å, largest atomic force at convergence
MAX_STEPS = 500  # FIRE2 steps per relaxation at most
BATCH_SIZE = 100  # structures relaxed together on the GPU
TIME_STEP = 0.5  # initial FIRE2 step, in ALCHEMI's internal time unit (10.18 fs)
GAMMA = 100  # kJ/mol, model collision energy of the AFIR force
NUMBER_OF_FINAL_STRUCTURES = 1  # the lowest final structures kept in final_structures.extxyz
BOND_TOLERANCE = 1.2  # two molecule atoms are bonded within BOND_TOLERANCE * (R_i + R_j)
SLAB_TAG = 0  # atom tags in configurations.extxyz
MOLECULE_TAG = 1
AFIR_R0 = 3.8164  # Å, GRRM17 Eq. (3)
AFIR_EPSILON = 1.0061  # kJ/mol, GRRM17 Eq. (3)

ALPHA = GAMMA * kJ / mol / ((2 ** (-1 / 6) - (1 + (1 + GAMMA / AFIR_EPSILON) ** 0.5) ** (-1 / 6)) * AFIR_R0)  # Eq. (3)
CATEGORY_BY_TAG = {SLAB_TAG: AtomCategory.SURFACE.value, MOLECULE_TAG: AtomCategory.GAS.value}
IN_PLANE_MASK = torch.tensor([1.0, 1.0, 0.0], device=DEVICE)
IN_PLANE_SHIFTS = torch.tensor([[a, b, 0.0] for a in (-1, 0, 1) for b in (-1, 0, 1)], device=DEVICE)
COVALENT_RADII = torch.tensor(covalent_radii, device=DEVICE, dtype=DTYPE)


def in_plane_minimum_image(vectors, cells):
    """
    Returns the shortest periodic image of each vector in the surface plane, a and b; there is no image along c.

    Args:
        vectors (torch.Tensor): Cartesian vectors, [P, 3], in Å.
        cells (torch.Tensor): The lattice vectors of each vector's structure, [P, 3, 3], rows a, b, c.

    Returns:
        torch.Tensor: The minimum-image vectors, [P, 3], in Å.
    """
    fractional = torch.einsum("pi,pij->pj", vectors, torch.linalg.inv(cells))
    fractional = fractional - torch.round(fractional) * IN_PLANE_MASK
    images = torch.einsum("psi,pij->psj", fractional.unsqueeze(1) + IN_PLANE_SHIFTS, cells)
    nearest = images.norm(dim=-1).argmin(dim=1)
    return torch.take_along_dim(images, nearest[:, None, None], dim=1).squeeze(1)


def afir_energy(positions, batch):
    """
    Returns the AFIR term of every structure in the batch, between its molecule and its slab atoms.

    GRRM17 Eq. (1), α Σ ω_ij r_ij / Σ ω_ij over molecule atoms i and slab atoms j, with ω_ij = ((R_i + R_j) / r_ij)^6
    (Eq. 2), R the covalent radii and r_ij at the minimum image in the surface plane; α is ALPHA, Eq. (3)
    (S. Maeda et al., J. Comput. Chem. 39, 233 (2018)).

    Args:
        positions (torch.Tensor): Atomic positions of the batch, [V, 3], in Å.
        batch (Batch): The batch, with atom_categories GAS for the molecule and SURFACE for the slab.

    Returns:
        torch.Tensor: The AFIR term of each structure, [B], in eV.
    """
    molecule_atoms = torch.where(batch.atom_categories == AtomCategory.GAS.value)[0]
    surface_atoms = torch.where(batch.atom_categories == AtomCategory.SURFACE.value)[0]
    molecule_index, surface_index = torch.where(
        batch.batch_idx[molecule_atoms][:, None] == batch.batch_idx[surface_atoms][None, :])
    pair_molecule_atoms, pair_surface_atoms = molecule_atoms[molecule_index], surface_atoms[surface_index]
    pair_structures = batch.batch_idx[pair_molecule_atoms]
    distances = in_plane_minimum_image(positions[pair_molecule_atoms] - positions[pair_surface_atoms],
                                       batch.cell[pair_structures]).norm(dim=-1)
    radii = (COVALENT_RADII[batch.atomic_numbers[pair_molecule_atoms]]
             + COVALENT_RADII[batch.atomic_numbers[pair_surface_atoms]])
    weights = (radii / distances) ** 6
    numerator = torch.zeros(batch.num_graphs, device=positions.device, dtype=positions.dtype)
    denominator = torch.zeros_like(numerator)
    return ALPHA * (numerator.index_add(0, pair_structures, weights * distances)
                    / denominator.index_add(0, pair_structures, weights))


def afir_bias(batch):
    """
    Returns the AFIR energy and forces of the batch, as BiasedPotentialHook expects them.

    Args:
        batch (Batch): The batch after the model's forward pass.

    Returns:
        Tuple[torch.Tensor, torch.Tensor]: Energy per structure, [B, 1], in eV, and force per atom, [V, 3],
        in eV/Å.
    """
    positions = batch.positions.clone().requires_grad_(True)
    energy = afir_energy(positions, batch)
    forces = -torch.autograd.grad(energy.sum(), positions)[0]
    return energy.detach().unsqueeze(-1), forces


def atomic_data(atoms):
    """
    Converts a configuration to ALCHEMI's AtomicData, its tags to atom categories: SLAB_TAG to SURFACE, MOLECULE_TAG
    to GAS.

    Args:
        atoms (ase.Atoms): The configuration, slab atoms tagged 0 and molecule atoms 1.

    Returns:
        AtomicData: The configuration on DEVICE, with zeroed forces and energy.
    """
    data = AtomicData.from_atoms(atoms, device=DEVICE, dtype=DTYPE)
    data["atom_categories"] = torch.tensor([CATEGORY_BY_TAG[tag] for tag in atoms.get_tags()], device=DEVICE)
    data["forces"] = torch.zeros_like(data.positions)
    data["energy"] = torch.zeros((1, 1), device=DEVICE, dtype=DTYPE)
    return data


def relaxed_atoms(original, relaxed_data):
    """
    Returns a copy of a structure at its relaxed positions, with its energy and forces.

    Args:
        original (ase.Atoms): The structure before the relaxation.
        relaxed_data (AtomicData): The same structure after it.

    Returns:
        ase.Atoms: The relaxed structure, energy and forces on a SinglePointCalculator.
    """
    atoms = original.copy()
    atoms.positions = relaxed_data.positions.cpu().numpy()
    atoms.calc = SinglePointCalculator(atoms, energy=float(relaxed_data.energy.item()),
                                       forces=relaxed_data.forces.cpu().numpy())
    return atoms


def relax_batch(ase_structures, model, bias_hooks):
    """
    Relaxes the structures as one batch with fixed-cell FIRE2, slab atoms frozen.

    Args:
        ase_structures (List[ase.Atoms]): The structures, slab atoms tagged 0 and molecule atoms 1.
        model (MACEWrapper): The MACE model.
        bias_hooks (List[BiasedPotentialHook]): Bias potentials added after each forward pass; [] for none.

    Returns:
        List[ase.Atoms]: The relaxed structures, in the input order.
    """
    optimizer = FIRE2(model=model, dt=TIME_STEP, n_steps=MAX_STEPS, convergence_hook=ConvergenceHook(
        criteria=[{"key": "forces", "threshold": FMAX, "reduce_op": "norm", "reduce_dims": -1}]))
    optimizer.register_hook(FreezeAtomsHook(freeze_category=AtomCategory.SURFACE.value))
    stage = FusedStage(sub_stages=[(0, optimizer)])
    for hook in model.make_neighbor_hooks():
        stage.register_hook(hook, stage=DynamicsStage.BEFORE_COMPUTE)
    for hook in bias_hooks:
        stage.register_hook(hook, stage=DynamicsStage.AFTER_COMPUTE)
    batch = stage.run(Batch.from_data_list([atomic_data(atoms) for atoms in ase_structures]))
    return [relaxed_atoms(atoms, relaxed_data) for atoms, relaxed_data in zip(ase_structures, batch.to_data_list())]


def relax(ase_structures, model, bias_hooks):
    """
    Relaxes all structures in batches of BATCH_SIZE, one after another, so the GPU memory a batch needs stays bounded.

    Args:
        ase_structures (List[ase.Atoms]): The structures, slab atoms tagged 0 and molecule atoms 1.
        model (MACEWrapper): The MACE model.
        bias_hooks (List[BiasedPotentialHook]): Bias potentials added after each forward pass; [] for none.

    Returns:
        List[ase.Atoms]: The relaxed structures, in the input order.
    """
    relaxed = []
    for start in range(0, len(ase_structures), BATCH_SIZE):
        end = min(start + BATCH_SIZE, len(ase_structures))
        logger.info("Relaxing structures {}–{} of {}", start + 1, end, len(ase_structures))
        relaxed += relax_batch(ase_structures[start:end], model, bias_hooks)
    return relaxed


def molecule_fragments(atoms):
    """
    Returns the number of fragments the molecule of a structure is in: 1 if intact, more if it split.

    Args:
        atoms (ase.Atoms): The structure, molecule atoms tagged 1.

    Returns:
        int: The number of connected groups of molecule atoms, bonded within BOND_TOLERANCE times their covalent radii.
    """
    return len(separate(atoms[atoms.get_tags() == MOLECULE_TAG], scale=BOND_TOLERANCE))


def energy_and_max_force(atoms):
    """
    Returns the energy of a structure, in eV, and the largest force on any of its atoms, in eV/Å.
    """
    return atoms.get_potential_energy(), np.linalg.norm(atoms.get_forces(), axis=1).max()


def plot_energies(energies, lowest_indices):
    """
    Plots the final energy of every configuration against its index, the kept lowest marked, to final_energies.png.

    Args:
        energies (List[float]): The final energy of each configuration, in eV.
        lowest_indices (List[int]): The indices of the kept lowest structures.
    """
    figure, axes = plt.subplots()
    axes.scatter(range(len(energies)), energies, s=12, label="all configurations")
    axes.scatter(lowest_indices, [energies[index] for index in lowest_indices], s=40, color="tab:red",
                 label=f"{len(lowest_indices)} lowest, kept")
    axes.set(xlabel="Configuration index", ylabel="Final energy (eV)")
    axes.ticklabel_format(axis="y", useOffset=False)
    axes.legend()
    figure.savefig("final_energies.png", dpi=150, bbox_inches="tight")


def write_results(afir_structures, final_structures):
    """
    Ranks the configurations by final energy, writes all of them to ranked_configurations.csv with the placement each
    started from (atoms.info["metadata"]["placement"]) and its molecule's fragments, the NUMBER_OF_FINAL_STRUCTURES
    lowest to final_structures.extxyz in that order, and the energies to final_energies.png.

    Args:
        afir_structures (List[ase.Atoms]): The structures after the relaxation under the AFIR force.
        final_structures (List[ase.Atoms]): The structures after the relaxation without it.
    """
    energies = [atoms.get_potential_energy() for atoms in final_structures]
    order = np.argsort(energies)
    with open("ranked_configurations.csv", "w", newline="") as results_file:
        writer = csv.writer(results_file)
        writer.writerow(["configuration", "rank", "afir_function_eV", "afir_max_force_eV_per_A", "energy_eV",
                         "max_force_eV_per_A", "rotation_axis_x", "rotation_axis_y", "rotation_axis_z",
                         "rotation_angle_deg", "position_u", "position_v", "molecule_fragments"])
        for rank, index in enumerate(order, start=1):
            placement = final_structures[index].info["metadata"]["placement"]
            writer.writerow([index, rank, *energy_and_max_force(afir_structures[index]),
                             *energy_and_max_force(final_structures[index]), *placement["rotation_axis"],
                             placement["rotation_angle_deg"], *placement["position"],
                             molecule_fragments(final_structures[index])])
            final_structures[index].info.update(rank=rank)
    lowest_indices = order[:NUMBER_OF_FINAL_STRUCTURES].tolist()
    write("final_structures.extxyz", [final_structures[index] for index in lowest_indices])
    plot_energies(energies, lowest_indices)


def main():
    """
    Relaxes the configurations of configurations.extxyz under the AFIR force, then without it, and writes the ranked
    results.
    """
    logger.info("AFIR force α, γ = {} kJ/mol: {:.3f} eV/Å", GAMMA, ALPHA)
    ase_structures = read("{{ JOB_WORK_DIR }}/configurations.extxyz", index=":")
    model = MACEWrapper.from_checkpoint(checkpoint_path=CHECKPOINT, device=torch.device(DEVICE), dtype=DTYPE,
                                        enable_cueq=True)
    logger.info("nvalchemi-toolkit {}, MACE with cuEquivariance", version("nvalchemi-toolkit"))
    afir_structures = relax(ase_structures, model, [BiasedPotentialHook(bias_fn=afir_bias)])
    final_structures = relax(afir_structures, model, [])
    write_results(afir_structures, final_structures)


if __name__ == "__main__":
    main()
