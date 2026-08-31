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
from mat3ra.made.tools.convert import to_ase
material = json.loads(r"""{{ MATERIAL | default({}) | tojson }}""")
molecule = to_ase(material)


# Defined reaction pairs (atom indices in the structure file)
BOND_FORMING_PAIR = (4, 5)
BOND_BREAKING_PAIR = (0, 1)

# AFIR and optimization parameters
AFIR_FORCE_RAMP = [1.0, 2.0, 3.0, 4.0]  # eV/Å
RELAXATION_FMAX = 0.03  # eV/Å
AFIR_FMAX = 0.05
SADDLE_FMAX = 0.02

# Resolved by mace-torch: a name from its catalogue, an https URL, or a file:// path.
# A name is downloaded once into ~/.cache/mace and needs no cluster-specific filesystem.
CHECKPOINT_PATH = "large-0b2"
MODEL_NAME = "mace-mp-0b2-large"
EV_TO_KCAL = 23.060548


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
        self.nl_hook = NeighborListHook(
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
        atomic_system = AtomicData.from_atoms(self.atoms, device=self.device)
        batch = Batch.from_data_list([atomic_system])

        # Generate neighbor list on the batch before model evaluation
        try:
            from nvalchemi.hooks import DynamicsContext

            context = DynamicsContext(batch=batch, step_count=0)
        except (ImportError, TypeError):
            from nvalchemi.hooks import HookContext

            context = HookContext(batch=batch)

        self.nl_hook(context, DynamicsStage.BEFORE_COMPUTE)

        # Evaluate model energy and forces
        outputs = self.model(batch)

        # Extract energy scalar cleanly
        raw_energy = outputs["energy"].detach().cpu().numpy()
        self.results["energy"] = float(
            raw_energy.item() if raw_energy.size == 1 else raw_energy.flat[0]
        )

        # Shape forces tensor strictly to (N_atoms, 3) expected by ASE
        raw_forces = outputs["forces"].detach().cpu().numpy()
        self.results["forces"] = raw_forces.reshape(-1, 3)


# Instantiate ALCHEMI Calculator
calculator = AlchemiMaceCalculator(checkpoint_path=CHECKPOINT_PATH, device=device)

# ==========================================
# 3. Relax Reactant Minimum
# ==========================================
reactant = molecule.copy()
reactant.calc = calculator

print("Relaxing initial reactant...")
opt = BFGS(reactant)
opt.run(fmax=RELAXATION_FMAX)
reactant_energy = reactant.get_potential_energy()
print(f"Reactant Energy: {reactant_energy:.3f} eV")

# ==========================================
# 4. Apply Artificial Force (AFIR)
# ==========================================
structure = reactant.copy()
structure.calc = calculator
afir_trajectory = [structure.copy()]
applied_alpha = [0.0]

print("\nRunning AFIR force ramp...")
for alpha in AFIR_FORCE_RAMP:
    structure.set_constraint(ExternalForce(*BOND_FORMING_PAIR, -alpha))

    opt = BFGS(structure, maxstep=0.1)
    opt.run(fmax=AFIR_FMAX, steps=150)

    afir_trajectory.append(structure.copy())
    applied_alpha.append(alpha)
    dist = structure.get_distance(*BOND_FORMING_PAIR)
    print(f"Force α = {alpha:.1f} eV/Å | Distance: {dist:.2f} Å")

structure.set_constraint()

# ==========================================
# 5. Extract Transition State (TS) Guess
# ==========================================
# Re-evaluate path energies without the constraint bias
unbiased_energies = []
forming_distances = []
breaking_distances = []
for img in afir_trajectory:
    img.set_constraint()
    img.calc = calculator
    unbiased_energies.append(img.get_potential_energy())
    forming_distances.append(img.get_distance(*BOND_FORMING_PAIR))
    breaking_distances.append(img.get_distance(*BOND_BREAKING_PAIR))

ts_guess_idx = int(np.argmax(unbiased_energies))
ts_guess = afir_trajectory[ts_guess_idx].copy()
ts_guess.calc = calculator

barrier_guess = (unbiased_energies[ts_guess_idx] - reactant_energy) * EV_TO_KCAL
print(
    f"\nTS Guess found at step {ts_guess_idx} with estimated barrier: {barrier_guess:.1f} kcal/mol"
)

# ==========================================
# 6. Refine TS with Dimer Method
# ==========================================
direction = np.zeros_like(ts_guess.positions)
for pair, sign in [(BOND_FORMING_PAIR, 1.0), (BOND_BREAKING_PAIR, -1.0)]:
    vec = ts_guess.positions[pair[1]] - ts_guess.positions[pair[0]]
    direction[pair[0]] += sign * (vec / np.linalg.norm(vec))
    direction[pair[1]] -= sign * (vec / np.linalg.norm(vec))
direction /= np.linalg.norm(direction)

dimer_control = DimerControl(
    initial_eigenmode_method="displacement", displacement_method="vector"
)
dimer = MinModeAtoms(ts_guess, dimer_control)
dimer.displace(displacement_vector=0.05 * direction)

dimer_opt = MinModeTranslate(dimer)
dimer_opt.run(fmax=SADDLE_FMAX, steps=200)

ts_energy = ts_guess.get_potential_energy()
activation_energy = (ts_energy - reactant_energy) * EV_TO_KCAL
print(f"Refined Activation Energy (Barrier): {activation_energy:.1f} kcal/mol")

write("transition_state.xyz", ts_guess)

ts_forming = ts_guess.get_distance(*BOND_FORMING_PAIR)
ts_breaking = ts_guess.get_distance(*BOND_BREAKING_PAIR)

# ==========================================
# 7. Verify Imaginary Frequencies
# ==========================================
vib = Vibrations(ts_guess, name="ts_vib")
vib.run()
freqs = vib.get_frequencies()

imaginary_freqs = [
    f.imag for f in freqs if np.iscomplex(f) and abs(f.imag) > 50
]
print(
    f"Found {len(imaginary_freqs)} imaginary frequency mode(s) > 50 cm^-1:"
)
for f in imaginary_freqs:
    print(f"  {f:.1f}i cm^-1")

vib.clean()

largest_imaginary = max((abs(f) for f in imaginary_freqs), default=0.0)
wall_time = time.time() - start_time

# ==========================================
# 8. Publish results
# ==========================================
relative_kcal = [
    (e - reactant_energy) * EV_TO_KCAL for e in unbiased_energies
]
steps = list(range(len(afir_trajectory)))

# --- afir_path.csv ------------------------------------------------
with open("afir_path.csv", "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
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
    for i in steps:
        writer.writerow(
            [
                i,
                f"{applied_alpha[i]:.6g}",
                f"{forming_distances[i]:.6g}",
                f"{breaking_distances[i]:.6g}",
                f"{unbiased_energies[i]:.6g}",
                f"{relative_kcal[i]:.6g}",
            ]
        )

# --- afir_energy_profile.png -------------------------------------
fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
ax.plot(steps, relative_kcal, "o-", color="#1f77b4", label="unbiased energy")
ax.plot(
    [ts_guess_idx],
    [relative_kcal[ts_guess_idx]],
    "o",
    color="#d62728",
    markersize=11,
    label=f"TS guess (step {ts_guess_idx})",
)
ax.axhline(
    activation_energy,
    color="#2ca02c",
    linestyle="--",
    label=f"refined barrier {activation_energy:.1f} kcal/mol",
)
ax.set_xlabel("AFIR step")
ax.set_ylabel("Energy relative to reactant (kcal/mol)")
ax.set_title("AFIR reaction path")
ax.set_xticks(steps)
ax.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig("afir_energy_profile.png")
plt.close(fig)

# --- afir_bond_distances.png -------------------------------------
fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
ax.plot(
    steps,
    forming_distances,
    "o-",
    color="#1f77b4",
    label=f"forming {BOND_FORMING_PAIR}",
)
ax.plot(
    steps,
    breaking_distances,
    "s-",
    color="#ff7f0e",
    label=f"breaking {BOND_BREAKING_PAIR}",
)
ax.axvline(ts_guess_idx, color="#d62728", linestyle=":", label="TS guess")
ax.set_xlabel("AFIR step")
ax.set_ylabel("Bond distance (A)")
ax.set_title("Reaction coordinate")
ax.set_xticks(steps)
ax.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig("afir_bond_distances.png")
plt.close(fig)

# --- results.csv --------------------------------------------------
results = {
    "Device": device,
    "Model": MODEL_NAME,
    "Activation energy (kcal/mol)": activation_energy,
    "Activation energy (eV)": ts_energy - reactant_energy,
    "Reactant energy (eV)": reactant_energy,
    "Transition state energy (eV)": ts_energy,
    "AFIR TS-guess barrier (kcal/mol)": barrier_guess,
    "TS guess step": ts_guess_idx,
    "Forming bond, reactant (A)": forming_distances[0],
    "Forming bond, TS (A)": ts_forming,
    "Breaking bond, reactant (A)": breaking_distances[0],
    "Breaking bond, TS (A)": ts_breaking,
    "Imaginary modes > 50 cm^-1": len(imaginary_freqs),
    "Largest imaginary frequency (cm^-1)": largest_imaginary,
    "Wall time (s)": wall_time,
}

# --- structures as Mat3ra materials --------------------------------
# from_ase keeps lattice, basis, metadata and hashes; an .xyz keeps only
# positions and symbols, so a Material rebuilt from one loses its provenance.
from mat3ra.made.material import Material
from mat3ra.made.tools.convert import from_ase

input_name = material.get("name", "molecule")
for atoms, label in ((molecule, "reactant"), (ts_guess, "transition_state")):
    out_material = Material.create(from_ase(atoms))
    out_material.name = f"{input_name} - {label.replace('_', ' ')}"
    with open(f"{label}.json", "w") as f:
        f.write(out_material.to_json())
    print(f"wrote {label}.json  ({out_material.name})")

with open("results.csv", "w", newline="") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=["Property", "Value"])
    writer.writeheader()
    for prop, val in results.items():
        print(f"{prop:<38} = {val}")
        writer.writerow(
            {
                "Property": prop,
                "Value": val if isinstance(val, str) else f"{val:.6g}",
            }
        )

PAYLOAD_KEYS = {
    "basis", "lattice", "isNonPeriodic", "formula", "unitCellFormula",
    "derivedProperties", "external", "src", "name", "description", "tags", "metadata",
}
ts_material = Material.create(from_ase(ts_guess))
ts_material.name = f"{input_name} - transition state"
print("---MATERIAL---")
print(json.dumps({k: v for k, v in ts_material.to_dict().items() if k in PAYLOAD_KEYS}))
print("---END---")
