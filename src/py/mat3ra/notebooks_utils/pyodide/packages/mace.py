import sys
import types
from importlib import import_module

from ...primitive.environment import is_pyodide_environment


def apply_patches():
    patch_mace_training()
    patch_mace_tools()


def patch_mace_training():
    """
    Stub lmdb and h5py packages.

    These are C-extension packages used by MACE's training/dataset code
    but not needed for inference. Stubs allow imports to succeed.
    """
    for package_name in ("lmdb", "h5py"):
        if package_name not in sys.modules:
            sys.modules[package_name] = types.ModuleType(package_name)

    print("✓ LMDB and HDF5 stubs applied")


def patch_mace_tools():
    """
    Fix MACE's torch_geometric import order issues in Pyodide.

    In Pyodide, torch_geometric.data may not be set during circular imports.
    Pre-importing ensures the attribute is available when MACE needs it.
    """
    try:
        torch_geometric = import_module("mace.tools.torch_geometric")
        torch_geometric_data = import_module("mace.tools.torch_geometric.data")
        torch_geometric.data = torch_geometric_data
        print("✓ MACE tools patches applied")
    except Exception as exc:
        print(f"⚠ MACE tools patches skipped: {exc}")


# Two MACE foundation model families are bundled under packages/models. They are named here after the
# chemistry they were trained on, rather than after the upstream acronyms:
#   "inorganic" - MACE-MP-0, trained on Materials Project crystal trajectories. MIT licensed.
#   "organic"   - MACE-OFF23 ("Organic Force Field"), trained on organic molecules.
#                 Academic Software License, which does not permit commercial use.
MODEL_PATHS_MAP = {
    "inorganic": {
        "small": "/drive/packages/models/2023-12-10-mace-128-L0_energy_epoch-249.model",
        "medium": "/drive/packages/models/2023-12-03-mace-128-L1_epoch-199.model",
        "large": "/drive/packages/models/MACE_MPtrj_2022.9.model",
    },
    "organic": {
        "small": "/drive/packages/models/MACE-OFF23_small.model",
        "medium": "/drive/packages/models/MACE-OFF23_medium.model",
        "large": "/drive/packages/models/MACE-OFF23_large.model",
    },
}
# Published name of each family, for labelling plots and saved results
MODEL_FAMILY_LABELS = {"inorganic": "MACE-MP-0", "organic": "MACE-OFF23"}
DEFAULT_MODEL_FAMILY = "inorganic"


def get_model_path(family: str, model: str) -> str:
    if family not in MODEL_PATHS_MAP:
        raise ValueError(f"Invalid MACE model family: {family!r}. Valid options are: {list(MODEL_PATHS_MAP)}")
    paths_for_family = MODEL_PATHS_MAP[family]
    if model not in paths_for_family:
        raise ValueError(f"Invalid MACE {family!r} model size: {model!r}. Valid options are: {list(paths_for_family)}")
    return paths_for_family[model]


def get_mace_model_pyodide(
    model: str, family: str = DEFAULT_MODEL_FAMILY, dispersion=False, default_dtype="float32", device="cpu", **kwargs
):
    mace_calculators = import_module("mace.calculators")
    return mace_calculators.MACECalculator(
        model_paths=get_model_path(family, model),
        dispersion=dispersion,
        default_dtype=default_dtype,
        device=device,
        **kwargs,
    )


def create_mace_calculator(
    model="large", family=DEFAULT_MODEL_FAMILY, dispersion=True, default_dtype="float32", device="cpu", **kwargs
):
    """
    Build a MACE calculator for the given model family and size.

    In JupyterLite the checkpoint is loaded from the models bundled with the platform (packages/models).
    Locally MACE resolves it through its own cache, downloading it once if it is not there yet.

    Args:
        model (str): Model size: "small", "medium" or "large".
        family (str): "inorganic" for crystals and surfaces, "organic" for molecules.
    """
    get_model_path(family, model)  # same validation in both environments

    if is_pyodide_environment():
        return get_mace_model_pyodide(
            model=model,
            family=family,
            dispersion=dispersion,
            default_dtype=default_dtype,
            device=device,
            **kwargs,
        )

    mace_calculators = import_module("mace.calculators")
    foundation_model = {"inorganic": mace_calculators.mace_mp, "organic": mace_calculators.mace_off}[family]
    return foundation_model(
        model=model,
        dispersion=dispersion,
        default_dtype=default_dtype,
        device=device,
        **kwargs,
    )
