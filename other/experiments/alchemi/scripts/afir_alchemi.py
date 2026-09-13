# ---------------------------------------------------------------- #
#                                                                  #
#  AFIR reaction-path search with ALCHEMI (MACE), Mat3ra platform. #
#                                                                  #
#  Material taken from the Material IO
#                                                                  #
# ---------------------------------------------------------------- #

import csv
import time


import matplotlib

matplotlib.use("Agg")  # no display on a compute node

import matplotlib.pyplot as plt
import numpy as np
import torch
from ase.calculators.calculator import Calculator, all_changes
from ase.constraints import ExternalForce
from ase.io import read, write
from ase.mep import DimerControl, MinModeAtoms, MinModeTranslate
from ase.optimize import BFGS
from ase.vibrations import Vibrations

# NVIDIA ALCHEMI Imports
from nvalchemi.data import AtomicData, Batch
from nvalchemi.dynamics import DynamicsStage
from nvalchemi.hooks import NeighborListHook
from nvalchemi.models.base import ModelConfig
from nvalchemi.models.mace import MACEWrapper


print(f"PyTorch version: {torch.__version__}")
print(f"CUDA compiled with PyTorch: {torch.version.cuda}")
print(f"Is CUDA available: {torch.cuda.is_available()}")


start_time = time.time()


device = "cuda:0" if torch.cuda.is_available() else "cpu"
if device.startswith("cuda"):
    torch.cuda.set_device(device)
print(f"Running simulation on: {device}")

# ==========================================
# 1. Direct Structure Loading & Settings
# ==========================================
import json
from mat3ra.made.material import Material
from mat3ra.made.tools.convert import to_ase

material = json.loads(r"""{{ MATERIAL | default({}) | tojson }}""")

# to_ase reads the basis as fractional coordinates. A material stored in cartesian
# units -- which is how the platform returns this one -- must be converted first, or
# every coordinate is multiplied by the lattice and the structure is torn apart.
input_material = Material.create(material)
input_material.to_crystal()
molecule = to_ase(input_material)

# to_ase routes through a pymatgen Structure, which is always periodic, so the input's
# isNonPeriodic never survives the trip and every exported structure comes back a crystal.
molecule.pbc = not material.get("isNonPeriodic", False)


# Defined reaction pairs (atom indices in the structure file)
BOND_FORMING_PAIR = (4, 5)
BOND_BREAKING_PAIR = (0, 1)

# AFIR and optimization parameters
AFIR_FORCE_STRENGTHS = [1.0, 2.0, 3.0, 4.0]  # eV/Å
RELAXATION_FMAX = 0.03  # eV/Å
AFIR_FMAX = 0.05
SADDLE_FMAX = 0.02

# Resolved by mace-torch: a name from its catalogue, an https URL, or a file:// path.
# A name is downloaded once into ~/.cache/mace and needs no cluster-specific filesystem.
CHECKPOINT_PATH = "large-0b2"
MODEL_NAME = "mace-mp-0b2-large"
EV_TO_KCAL_PER_MOL = 23.060548


# ==========================================
# 2. ALCHEMI MACE ASE Calculator Adapter
# ==========================================
class AlchemiMaceCalculator(Calculator):
    """ASE Calculator adapter wrapping NVIDIA ALCHEMI MACE and NeighborListHook."""

    implemented_properties = ["energy", "forces"]

    def __init__(self, checkpoint_path, device="cuda:0", **kwargs):
        super().__init__(**kwargs)
        self.device = device

        # 1. Model output configuration
        model_config = ModelConfig(outputs=frozenset({"energy", "forces"}))

        # 2. Initialize ALCHEMI MACE model
        self.model = MACEWrapper.from_checkpoint(
            checkpoint_path=checkpoint_path,
            model_config=model_config,
            device=self.device,
        ).eval()

        # 3. Neighbor list hook using model's neighbor config
        self.neighbor_list_hook = NeighborListHook(
            config=self.model.model_config.neighbor_config,
            stage=DynamicsStage.BEFORE_COMPUTE,
        )

    def calculate(
        self,
        atoms=None,
        properties=["energy", "forces"],
        system_changes=all_changes,
    ):
        super().calculate(atoms, properties, system_changes)

        # Convert ASE Atoms -> ALCHEMI AtomicData -> Batch
        atomic_data = AtomicData.from_atoms(self.atoms, device=self.device)
        batch = Batch.from_data_list([atomic_data])

        # Generate neighbor list on the batch before model evaluation
        try:
            from nvalchemi.hooks import DynamicsContext

            context = DynamicsContext(batch=batch, step_count=0)
        except (ImportError, TypeError):
            from nvalchemi.hooks import HookContext

            context = HookContext(batch=batch)

        self.neighbor_list_hook(context, DynamicsStage.BEFORE_COMPUTE)

        # Evaluate model energy and forces
        outputs = self.model(batch)

        # Extract energy scalar cleanly
        energy_output = outputs["energy"].detach().cpu().numpy()
        self.results["energy"] = float(
            energy_output.item() if energy_output.size == 1 else energy_output.flat[0]
        )

        # Shape forces tensor strictly to (N_atoms, 3) expected by ASE
        forces_output = outputs["forces"].detach().cpu().numpy()
        self.results["forces"] = forces_output.reshape(-1, 3)


# Instantiate ALCHEMI Calculator
calculator = AlchemiMaceCalculator(checkpoint_path=CHECKPOINT_PATH, device=device)

# ==========================================
# 3. Relax Reactant Minimum
# ==========================================
reactant = molecule.copy()
reactant.calc = calculator

print("Relaxing initial reactant...")
optimizer = BFGS(reactant)
optimizer.run(fmax=RELAXATION_FMAX)
reactant_energy = reactant.get_potential_energy()
print(f"Reactant Energy: {reactant_energy:.3f} eV")

# ==========================================
# 4. Apply Artificial Force (AFIR)
# ==========================================
structure = reactant.copy()
structure.calc = calculator
afir_trajectory = [structure.copy()]
applied_force_strengths = [0.0]

print("\nRunning AFIR force ramp...")
for force_strength in AFIR_FORCE_STRENGTHS:
    structure.set_constraint(ExternalForce(*BOND_FORMING_PAIR, -force_strength))

    optimizer = BFGS(structure, maxstep=0.1)
    optimizer.run(fmax=AFIR_FMAX, steps=150)

    afir_trajectory.append(structure.copy())
    applied_force_strengths.append(force_strength)
    forming_distance = structure.get_distance(*BOND_FORMING_PAIR)
    print(f"Force α = {force_strength:.1f} eV/Å | Distance: {forming_distance:.2f} Å")

structure.set_constraint()

# ==========================================
# 5. Extract Transition State (TS) Guess
# ==========================================
# Re-evaluate path energies without the constraint bias
unbiased_energies = []
forming_distances = []
breaking_distances = []
for image in afir_trajectory:
    image.set_constraint()
    image.calc = calculator
    unbiased_energies.append(image.get_potential_energy())
    forming_distances.append(image.get_distance(*BOND_FORMING_PAIR))
    breaking_distances.append(image.get_distance(*BOND_BREAKING_PAIR))

transition_state_index = int(np.argmax(unbiased_energies))
transition_state = afir_trajectory[transition_state_index].copy()
transition_state.calc = calculator

estimated_barrier = (unbiased_energies[transition_state_index] - reactant_energy) * EV_TO_KCAL_PER_MOL
print(
    f"\nTS Guess found at step {transition_state_index} with estimated barrier: {estimated_barrier:.1f} kcal/mol"
)

# ==========================================
# 6. Refine TS with Dimer Method
# ==========================================
direction = np.zeros_like(transition_state.positions)
for pair, sign in [(BOND_FORMING_PAIR, 1.0), (BOND_BREAKING_PAIR, -1.0)]:
    bond_vector = transition_state.positions[pair[1]] - transition_state.positions[pair[0]]
    direction[pair[0]] += sign * (bond_vector / np.linalg.norm(bond_vector))
    direction[pair[1]] -= sign * (bond_vector / np.linalg.norm(bond_vector))
direction /= np.linalg.norm(direction)

dimer_control = DimerControl(
    initial_eigenmode_method="displacement", displacement_method="vector"
)
dimer = MinModeAtoms(transition_state, dimer_control)
dimer.displace(displacement_vector=0.05 * direction)

dimer_opt = MinModeTranslate(dimer)
dimer_opt.run(fmax=SADDLE_FMAX, steps=200)

transition_state_energy = transition_state.get_potential_energy()
activation_energy = (transition_state_energy - reactant_energy) * EV_TO_KCAL_PER_MOL
print(f"Refined Activation Energy (Barrier): {activation_energy:.1f} kcal/mol")

write("transition_state.xyz", transition_state)

transition_state_forming_distance = transition_state.get_distance(*BOND_FORMING_PAIR)
transition_state_breaking_distance = transition_state.get_distance(*BOND_BREAKING_PAIR)

# ==========================================
# 7. Verify Imaginary Frequencies
# ==========================================
vibrations = Vibrations(transition_state, name="transition_state_vibrations")
vibrations.run()
frequencies = vibrations.get_frequencies()

imaginary_frequencies = [
    frequency.imag
    for frequency in frequencies
    if np.iscomplex(frequency) and abs(frequency.imag) > 50
]
print(
    f"Found {len(imaginary_frequencies)} imaginary frequency mode(s) > 50 cm^-1:"
)
for frequency in imaginary_frequencies:
    print(f"  {frequency:.1f}i cm^-1")

vibrations.clean()

largest_imaginary_frequency = max(
    (abs(frequency) for frequency in imaginary_frequencies), default=0.0
)
# ==========================================
# 8. Relax the Product
# ==========================================
# The last image of the biased path, relaxed without the artificial force, falls into
# the product minimum the search reached. The constraint was already cleared in step 5.
product = afir_trajectory[-1].copy()
product.calc = calculator

print("\nRelaxing the discovered product...")
BFGS(product).run(fmax=RELAXATION_FMAX)
product_energy = product.get_potential_energy()
reaction_energy = (product_energy - reactant_energy) * EV_TO_KCAL_PER_MOL
print(f"Reaction energy: {reaction_energy:.1f} kcal/mol relative to the reactant")

wall_time = time.time() - start_time

# ==========================================
# 9. Publish results
# ==========================================
relative_energies_kcal = [
    (e - reactant_energy) * EV_TO_KCAL_PER_MOL for e in unbiased_energies
]
step_indices = list(range(len(afir_trajectory)))

# --- afir_path.csv ------------------------------------------------
with open("afir_path.csv", "w", newline="") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerow(
        [
            "Step",
            "Applied force (eV/A)",
            "Forming bond (A)",
            "Breaking bond (A)",
            "Energy (eV)",
            "Relative energy (kcal/mol)",
        ]
    )
    for i in step_indices:
        writer.writerow(
            [
                i,
                f"{applied_force_strengths[i]:.6g}",
                f"{forming_distances[i]:.6g}",
                f"{breaking_distances[i]:.6g}",
                f"{unbiased_energies[i]:.6g}",
                f"{relative_energies_kcal[i]:.6g}",
            ]
        )

# --- afir_energy_profile.png -------------------------------------
figure, axes = plt.subplots(figsize=(6, 4), dpi=150)
axes.plot(step_indices, relative_energies_kcal, "o-", color="#1f77b4", label="unbiased energy")
axes.plot(
    [transition_state_index],
    [relative_energies_kcal[transition_state_index]],
    "o",
    color="#d62728",
    markersize=11,
    label=f"TS guess (step {transition_state_index})",
)
axes.axhline(
    activation_energy,
    color="#2ca02c",
    linestyle="--",
    label=f"refined barrier {activation_energy:.1f} kcal/mol",
)
axes.set_xlabel("AFIR step")
axes.set_ylabel("Energy relative to reactant (kcal/mol)")
axes.set_title("AFIR reaction path")
axes.set_xticks(step_indices)
axes.legend(frameon=False, fontsize=8)
figure.tight_layout()
figure.savefig("afir_energy_profile.png")
plt.close(figure)

# --- afir_bond_distances.png -------------------------------------
figure, axes = plt.subplots(figsize=(6, 4), dpi=150)
axes.plot(
    step_indices,
    forming_distances,
    "o-",
    color="#1f77b4",
    label=f"forming {BOND_FORMING_PAIR}",
)
axes.plot(
    step_indices,
    breaking_distances,
    "s-",
    color="#ff7f0e",
    label=f"breaking {BOND_BREAKING_PAIR}",
)
axes.axvline(transition_state_index, color="#d62728", linestyle=":", label="TS guess")
axes.set_xlabel("AFIR step")
axes.set_ylabel("Bond distance (A)")
axes.set_title("Reaction coordinate")
axes.set_xticks(step_indices)
axes.legend(frameon=False, fontsize=8)
figure.tight_layout()
figure.savefig("afir_bond_distances.png")
plt.close(figure)

# --- results.csv --------------------------------------------------
results = {
    "Device": device,
    "Model": MODEL_NAME,
    "Activation energy (kcal/mol)": activation_energy,
    "Activation energy (eV)": transition_state_energy - reactant_energy,
    "Reaction energy (kcal/mol)": reaction_energy,
    "Reactant energy (eV)": reactant_energy,
    "Transition state energy (eV)": transition_state_energy,
    "AFIR TS-guess barrier (kcal/mol)": estimated_barrier,
    "TS guess step": transition_state_index,
    "Forming bond, reactant (A)": forming_distances[0],
    "Forming bond, TS (A)": transition_state_forming_distance,
    "Breaking bond, reactant (A)": breaking_distances[0],
    "Breaking bond, TS (A)": transition_state_breaking_distance,
    "Forming bond, product (A)": product.get_distance(*BOND_FORMING_PAIR),
    "Breaking bond, product (A)": product.get_distance(*BOND_BREAKING_PAIR),
    "Imaginary modes > 50 cm^-1": len(imaginary_frequencies),
    "Largest imaginary frequency (cm^-1)": largest_imaginary_frequency,
    "Wall time (s)": wall_time,
}

# --- structures as Mat3ra materials --------------------------------
# from_ase keeps lattice, basis, metadata and hashes; an .xyz keeps only
# positions and symbols, so a Material rebuilt from one loses its provenance.
from mat3ra.made.material import Material
from mat3ra.made.tools.convert import from_ase

input_material_name = material.get("name", "molecule")
for atoms, label in ((molecule, "reactant"), (transition_state, "transition_state")):
    output_material = Material.create(from_ase(atoms))
    output_material.name = f"{input_material_name} - {label.replace('_', ' ')}"
    with open(f"{label}.json", "w") as material_file:
        material_file.write(output_material.to_json())
    print(f"wrote {label}.json  ({output_material.name})")

with open("results.csv", "w", newline="") as csv_file:
    writer = csv.DictWriter(csv_file, fieldnames=["Property", "Value"])
    writer.writeheader()
    for property_name, value in results.items():
        print(f"{property_name:<38} = {value}")
        writer.writerow(
            {
                "Property": property_name,
                "Value": value if isinstance(value, str) else f"{value:.6g}",
            }
        )

MATERIAL_PAYLOAD_KEYS = {
    "basis", "lattice", "isNonPeriodic", "formula", "unitCellFormula",
    "derivedProperties", "external", "src", "name", "description", "tags", "metadata",
}
# MaterialDAO tags a job-produced structure "jobId-<id>" (MaterialDAO.ts:650). Following
# that convention means these are found the same way as platform-created structures.
JOB_TAG = "jobId-{{ JOB_ID }}"


def build_material_payload(atoms, role):
    output_material = Material.create(from_ase(atoms))
    output_material.name = f"{input_material_name} - {role}"
    payload = {
        key: value
        for key, value in output_material.to_dict().items()
        if key in MATERIAL_PAYLOAD_KEYS
    }
    payload["tags"] = [JOB_TAG]
    # The REST layer reads the account from owner._id, and falls back to the calling
    # user's default account when it is absent -- which fails for a workflow-issued
    # request. The input material already carries the right owner, so reuse it.
    if material.get("owner"):
        payload["owner"] = material["owner"]
    return payload


exported_structures = {
    "transition_state": build_material_payload(transition_state, "transition state"),
    "product": build_material_payload(product, "product"),
}

print("---MATERIALS---")
print(json.dumps(exported_structures))
print("---END---")
