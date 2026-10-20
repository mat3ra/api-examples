#!/usr/bin/env python3
"""Relaxes the job's materials with METHOD and writes its timing row to results.csv.
Pipeline time excludes model loading, warmup, and file I/O."""

import csv
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import torch
from ase.calculators.singlepoint import SinglePointCalculator
from ase.filters import FrechetCellFilter
from ase.optimize import FIRE2
from loguru import logger
from mace.calculators import mace_mp
from mat3ra.made.material import Material
from mat3ra.made.tools.convert import to_ase
from nvalchemi.data import AtomicData, Batch
from nvalchemi.dynamics import FIRE2VariableCell, FusedStage, HostMemory, SizeAwareSampler
from nvalchemi.dynamics.base import ConvergenceHook, DynamicsStage
from nvalchemi.models.mace import MACEWrapper

METHOD = "ALCHEMI batched"
DEVICE = "cuda:0"
CHECKPOINT = "medium-mpa-0"
DTYPE = "float32"
FMAX = 0.03  # eV/A, on atomic forces only
MAX_STEPS = 500
TIME_STEP = 0.5
BATCH_SIZE = 10
MATERIALS = json.loads(r"""{{ MATERIALS | default([]) | tojson }}""")
MATERIAL_IDS = json.loads(r"""{{ MATERIAL_IDS | default([]) | tojson }}""")

FIELDS = ("method", "structures", "pipeline_seconds", "structures_per_second",
          "model_load_s", "warmup_s", "input_prepare_s", "optimizer_setup_s",
          "optimize_collect_s", "result_materialization_s")
PIPELINE_FIELDS = ("input_prepare_s", "optimizer_setup_s", "optimize_collect_s",
                   "result_materialization_s")


def synchronize(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


@contextmanager
def timed_phase(phases, name, device):
    synchronize(device)
    start = time.perf_counter()
    try:
        yield
    finally:
        synchronize(device)
        phases[name] = phases.get(name, 0.0) + time.perf_counter() - start


def timed(device, action):
    synchronize(device)
    start = time.perf_counter()
    result = action()
    synchronize(device)
    return result, time.perf_counter() - start


def atomic_data(structures, device, dtype):
    data_list = []
    for i, atoms in enumerate(structures):
        data = AtomicData.from_atoms(atoms, device=device, dtype=dtype)
        data.add_system_property("structure_id", torch.tensor([[i]], device=device,
                                                        dtype=torch.long))
        data["forces"] = torch.zeros_like(data.positions)
        data["energy"] = torch.zeros((1, 1), device=device, dtype=dtype)
        data["stress"] = torch.zeros((1, 3, 3), device=device, dtype=dtype)
        data["velocities"] = torch.zeros_like(data.positions)
        data_list.append(data)
    return data_list


def initialize_runtime_fields(batch):
    batch["forces"] = torch.zeros_like(batch.positions)
    batch["energy"] = torch.zeros((batch.num_graphs, 1), device=batch.device,
                                  dtype=batch.positions.dtype)
    batch["stress"] = torch.zeros((batch.num_graphs, 3, 3), device=batch.device,
                                  dtype=batch.positions.dtype)
    batch["velocities"] = torch.zeros_like(batch.positions)


def alchemi_optimizer(model, device, fmax, steps, dt, fused):
    optimizer = FIRE2VariableCell(
        model=model, dt=dt, n_steps=steps, device_type=device.type,
        convergence_hook=ConvergenceHook(criteria=[{
            "key": "forces", "threshold": fmax, "reduce_op": "norm", "reduce_dims": -1,
        }]),
    )
    if not fused:
        optimizer.register_hook(optimizer.convergence_hook)
        for hook in model.make_neighbor_hooks():
            optimizer.register_hook(hook, stage=DynamicsStage.BEFORE_COMPUTE)
    return optimizer


def log_alchemi_completion(row, mode, steps, fmax):
    maximum = float(torch.linalg.vector_norm(row.forces, dim=-1).max().item())
    logger.info("{} structure_id={} energy={:+.6f} eV fmax={:.6f} eV/A "
                "steps={} status={}", mode, int(row.structure_id.item()),
                float(row.energy.item()), maximum, steps,
                "converged" if maximum < fmax else "max_steps")


class StructureDataset:
    def __init__(self, structures, device, dtype):
        self.data_list = atomic_data(structures, device, dtype)

    def __len__(self):
        return len(self.data_list)

    def __getitem__(self, index):
        return self.data_list[index].clone(), {}

    def get_metadata(self, index):
        return self.data_list[index].num_nodes, 0


class CompletionSink(HostMemory):
    def __init__(self, capacity, fmax, max_steps, log_results):
        super().__init__(capacity)
        self.fmax = fmax
        self.max_steps = max_steps
        self.log_results = log_results

    def write(self, batch, mask=None):
        previous = len(self._data_list)
        super().write(batch, mask=mask)
        if self.log_results:
            for row in self._data_list[previous:]:
                counter = getattr(row, "n_steps_counter_0", None)
                steps = int(counter.item()) if counter is not None and counter.item() else self.max_steps
                log_alchemi_completion(row, "inflight", steps, self.fmax)


def relax_inflight(structures, model, device, dtype, fmax, steps, dt, batch_size,
                   *, warmup_only=False):
    phases = {}
    with timed_phase(phases, "input_prepare_s", device):
        dataset = StructureDataset(structures, device, dtype)
    with timed_phase(phases, "optimizer_setup_s", device):
        sampler = SizeAwareSampler(dataset, max_batch_size=batch_size, shuffle=False)
        sink = CompletionSink(len(structures), fmax, steps, not warmup_only)
        optimizer = alchemi_optimizer(model, device, fmax, steps, dt, fused=True)
        stage = FusedStage(sub_stages=[(0, optimizer)], sampler=sampler, sinks=[sink],
                           init_fn=initialize_runtime_fields, device_type=device.type,
                           refill_frequency=1)
        for hook in model.make_neighbor_hooks():
            stage.register_hook(hook, stage=DynamicsStage.BEFORE_COMPUTE)
    with timed_phase(phases, "optimize_collect_s", device):
        remainder = stage.run(n_steps=1 if warmup_only else None)
        result = None if warmup_only else sink.read()
    if not warmup_only and remainder is not None:
        raise RuntimeError("Inflight optimization ended before all results were collected")
    return result, phases


def relax_alchemi_serial(structures, model, device, dtype, fmax, steps, dt,
                         *, warmup_only=False):
    phases = {}
    with timed_phase(phases, "input_prepare_s", device):
        data_list = atomic_data(structures, device, dtype)
    completed = []
    for data in data_list:
        with timed_phase(phases, "optimizer_setup_s", device):
            batch = Batch.from_data_list([data])
            initialize_runtime_fields(batch)
            batch["status"] = torch.zeros((1, 1), device=device, dtype=torch.long)
            optimizer = alchemi_optimizer(model, device, fmax, steps, dt, fused=False)
        with timed_phase(phases, "optimize_collect_s", device):
            optimizer._call_hooks(DynamicsStage.BEFORE_COMPUTE, batch)
            optimizer.compute(batch)
            result = optimizer.run(batch, n_steps=1 if warmup_only else None)
            row = result.to_data_list()[0]
            completed.append(row)
            if not warmup_only:
                log_alchemi_completion(row, "serial", optimizer.step_count, fmax)
    with timed_phase(phases, "optimize_collect_s", device):
        result = Batch.from_data_list(completed)
    return result, phases


def materialize_alchemi(batch, structures, fmax):
    rows = batch.to_data_list()
    if len(rows) != len(structures):
        raise RuntimeError(f"Expected {len(structures)} ALCHEMI results, got {len(rows)}")
    by_id = {int(row.structure_id.item()): row for row in rows}
    if set(by_id) != set(range(len(structures))):
        raise RuntimeError("Missing or duplicate ALCHEMI structure IDs")
    relaxed = []
    for i, original in enumerate(structures):
        row = by_id[i]
        atoms = original.copy()
        atoms.set_cell(row.cell.detach().cpu().numpy().reshape(3, 3), scale_atoms=False)
        atoms.positions = row.positions.detach().cpu().numpy()
        energy = float(row.energy.item())
        forces = row.forces.detach().cpu().numpy()
        maximum = float(np.linalg.norm(forces, axis=-1).max())
        atoms.calc = SinglePointCalculator(atoms, energy=energy, forces=forces)
        if maximum >= fmax:
            raise RuntimeError(f"ALCHEMI structure {i} did not converge: fmax={maximum}")
        relaxed.append(atoms)
    return relaxed


class AtomicForceFIRE2(FIRE2):
    def gradient_converged(self, gradient):
        forces = self.atoms.atoms.get_forces()
        return bool(np.linalg.norm(forces, axis=1).max() < self.fmax)


def ase_optimizer(atoms, dt):
    filtered = FrechetCellFilter(atoms)
    return filtered, AtomicForceFIRE2(filtered, dt=dt, logfile=None)


def relax_ase(structures, calculator, device, fmax, steps, dt):
    phases = dict.fromkeys(PIPELINE_FIELDS, 0.0)
    relaxed = []
    for i, original in enumerate(structures):
        def prepare():
            atoms = original.copy()
            atoms.calc = calculator
            return atoms
        atoms, duration = timed(device, prepare)
        phases["input_prepare_s"] += duration
        (_, optimizer), duration = timed(device, lambda: ase_optimizer(atoms, dt))
        phases["optimizer_setup_s"] += duration

        def optimize_collect():
            converged = optimizer.run(fmax=fmax, steps=steps)
            energy = float(atoms.get_potential_energy())
            forces = atoms.get_forces()
            stress = atoms.get_stress(voigt=False)
            return converged, energy, forces, stress
        (converged, energy, forces, stress), duration = timed(device, optimize_collect)
        phases["optimize_collect_s"] += duration

        def materialize():
            maximum = float(np.linalg.norm(forces, axis=1).max())
            saved = atoms.copy()
            saved.calc = SinglePointCalculator(saved, energy=energy, forces=forces,
                                               stress=stress)
            logger.info("ASE structure_id={} energy={:+.6f} eV fmax={:.6f} eV/A "
                        "steps={} status={}", i, energy, maximum, optimizer.nsteps,
                        "converged" if converged and maximum < fmax else "max_steps")
            if not converged or maximum >= fmax:
                raise RuntimeError(f"ASE structure {i} did not converge: fmax={maximum}")
            return saved
        saved, duration = timed(device, materialize)
        phases["result_materialization_s"] += duration
        relaxed.append(saved)
    return relaxed, phases


def make_row(method, count, model_load, warmup, phases):
    pipeline = sum(phases[key] for key in PIPELINE_FIELDS)
    return {"method": method, "structures": count,
            "pipeline_seconds": pipeline, "structures_per_second": count / pipeline,
            "model_load_s": model_load, "warmup_s": warmup,
            **{key: phases[key] for key in PIPELINE_FIELDS}}


def load_model(device, dtype):
    checkpoint = CHECKPOINT
    if Path(checkpoint).is_file():
        checkpoint = Path(checkpoint).resolve().as_uri()
    with torch.serialization.safe_globals([slice]):
        model = MACEWrapper.from_checkpoint(checkpoint_path=checkpoint,
                                            device=device, dtype=dtype).eval()
    model.model_config.active_outputs = {"energy", "forces", "stress"}
    return model


def run_alchemi_batched(device, structures):
    dtype = getattr(torch, DTYPE)
    model, model_load = timed(device, lambda: load_model(device, dtype))
    _, warmup = timed(device, lambda: relax_inflight(
        structures[:1], model, device, dtype, FMAX, MAX_STEPS, TIME_STEP,
        batch_size=1, warmup_only=True))
    batch, phases = relax_inflight(structures, model, device, dtype,
                                   FMAX, MAX_STEPS, TIME_STEP, BATCH_SIZE)
    _, duration = timed(device, lambda: materialize_alchemi(batch, structures, FMAX))
    phases["result_materialization_s"] = duration
    return model_load, warmup, phases


def run_alchemi_serial(device, structures):
    dtype = getattr(torch, DTYPE)
    model, model_load = timed(device, lambda: load_model(device, dtype))
    _, warmup = timed(device, lambda: relax_alchemi_serial(
        structures[:1], model, device, dtype, FMAX, MAX_STEPS, TIME_STEP,
        warmup_only=True))
    batch, phases = relax_alchemi_serial(structures, model, device, dtype, FMAX,
                                         MAX_STEPS, TIME_STEP)
    _, duration = timed(device, lambda: materialize_alchemi(batch, structures, FMAX))
    phases["result_materialization_s"] = duration
    return model_load, warmup, phases


def run_ase_serial(device, structures):
    calculator, model_load = timed(device, lambda: mace_mp(
        model=CHECKPOINT, device=str(device), default_dtype=DTYPE))

    def ase_warmup():
        atoms = structures[0].copy()
        atoms.positions[0, 0] += 1e-4
        atoms.calc = calculator
        atoms.get_potential_energy()
        atoms.get_forces()
        atoms.get_stress()
        _, optimizer = ase_optimizer(atoms, TIME_STEP)
        optimizer.run(fmax=0.0, steps=1)
    _, warmup = timed(device, ase_warmup)
    _, phases = relax_ase(structures, calculator, device, FMAX, MAX_STEPS, TIME_STEP)
    return model_load, warmup, phases


RUNS = {"ALCHEMI batched": run_alchemi_batched, "ALCHEMI serial": run_alchemi_serial,
        "ASE serial": run_ase_serial}


def main():
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    device = torch.device(DEVICE)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    materials_by_id = {material["_id"]: material for material in MATERIALS}
    structures = []
    for material_id in MATERIAL_IDS:
        material = Material.create(materials_by_id[material_id])
        material.to_crystal()
        structures.append(to_ase(material))
    logger.info("{} case: {} structures, {} atoms each, pbc={}", METHOD, len(structures),
                len(structures[0]), structures[0].pbc.tolist())
    model_load, warmup, phases = RUNS[METHOD](device, structures)
    with open("results.csv", "w", newline="") as results_file:
        writer = csv.DictWriter(results_file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(make_row(METHOD, len(structures), model_load, warmup, phases))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("Benchmark failed: {}", exc)
        sys.exit(1)
