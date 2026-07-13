# Mat3ra API Examples

## Contents of this Repository

### API Examples (`examples/`)

Notebooks demonstrating the Mat3ra REST API, in roughly the order a new user should follow.

| Folder | Notebook | Description |
|--------|----------|-------------|
| [system](examples/system/) | [Get Authentication Params](examples/system/get_authentication_params.ipynb) | Authenticate via OIDC and inspect account credentials. |
| [material](examples/material/) | [Get Materials by Formula](examples/material/get_materials_by_formula.ipynb) | Query materials stored on your account by chemical formula. |
| [material](examples/material/) | [Create Material](examples/material/create_material.ipynb) | Generate a material in [JSON format](https://docs.mat3ra.com/materials/data/) and upload it to your account. |
| [material](examples/material/) | [Import Materials from POSCAR](examples/material/upload_materials_from_file_poscar.ipynb) | Import materials directly from POSCAR files. |
| [workflow](examples/workflow/) | [Get Workflows](examples/workflow/get_workflows.ipynb) | [Query](https://docs.mat3ra.com/rest-api/query-structure/) the API to search for workflows by type. |
| [workflow](examples/workflow/) | [Quantum Espresso Workflow and Job](examples/workflow/qe_scf_calculation.ipynb) | Create a QE workflow from an input file, submit a job, and post-process results. |
| [job](examples/job/) | [Create and Submit Job](examples/job/create_and_submit_job.ipynb) | Create and run a DFT job via the API. |
| [job](examples/job/) | [Get File from Job](examples/job/get-file-from-job.ipynb) | Query job output files and download them to disk. |
| [job](examples/job/) | [Run Simulations and Extract Properties](examples/job/run-simulations-and-extract-properties.ipynb) | Copy a [bank workflow](https://docs.mat3ra.com/workflows/bank/) and calculate [band gaps](https://docs.mat3ra.com/properties-directory/non-scalar/band-gaps/) for multiple materials. |
| [job](examples/job/) | [ML — Train Model and Predict Properties](examples/job/ml-train-model-predict-properties.ipynb) | Generate a training dataset, train an [ML model](https://docs.mat3ra.com/software-directory/overview/#machine-learning), and predict band gaps. |
| [reproducing_publications](examples/reproducing_publications/) | [Band Gaps — Twisted MoS₂](examples/reproducing_publications/band_gaps_for_interface_bilayer_twisted_molybdenum_disulfide.ipynb) | Reproduce band gap results for bilayer twisted MoS₂ interfaces. |
| [reproducing_publications](examples/reproducing_publications/) | [Band Structure — Twisted MoS₂](examples/reproducing_publications/band_structure_for_interface_bilayer_twisted_molybdenum_disulfide.ipynb) | Reproduce band structure results for bilayer twisted MoS₂ interfaces. |

### Materials Designer Notebooks (`other/materials_designer/`)

Notebooks run inside the [Materials Designer](https://docs.mat3ra.com/materials-designer/overview/) tool to create and transform material structures.

| Notebook | Description |
|----------|-------------|
| [Introduction](other/materials_designer/Introduction.ipynb) | Overview of the Materials Designer notebook environment. |
| [Create Slab](other/materials_designer/create_slab.ipynb) | Generate surface slab models. |
| [Create Supercell](other/materials_designer/create_supercell.ipynb) | Build supercells from a unit cell. |
| [Create Interface (ZSL)](other/materials_designer/create_interface_with_min_strain_zsl.ipynb) | Interface with minimum strain via the ZSL algorithm. |
| [Create Interface (no strain)](other/materials_designer/create_interface_with_no_strain_matching.ipynb) | Interface without strain matching. |
| [Create Interface (ASE/EMT relaxation)](other/materials_designer/create_interface_with_relaxation_ase_emt.ipynb) | Interface with ASE/EMT relaxation. |
| [Create Heterostructure](other/materials_designer/create_heterostructure_example.ipynb) | Assemble a van-der-Waals heterostructure. |
| [Create Twisted Interface](other/materials_designer/create_twisted_interface_with_commensurate_lattices.ipynb) | Twisted interface using commensurate lattices. |
| [Create Twisted Interface (nanoribbons)](other/materials_designer/create_twisted_interface_with_nanoribbons.ipynb) | Twisted interface from nanoribbon building blocks. |
| [Create Grain Boundary (crystal)](other/materials_designer/create_grain_boundary_crystal.ipynb) | Grain boundary in a bulk crystal. |
| [Create Grain Boundary (film)](other/materials_designer/create_grain_boundary_film.ipynb) | Grain boundary in a thin film. |
| [Create Nanoribbon](other/materials_designer/create_nanoribbon.ipynb) | Generate a nanoribbon structure. |
| [Create Nanowire](other/materials_designer/create_nanowire.ipynb) | Generate a nanowire structure. |
| [Create Nanowire (custom shape)](other/materials_designer/create_nanowire_custom_shape.ipynb) | Nanowire with a user-defined cross-section. |
| [Create Monolayer](other/materials_designer/create_monolayer.ipynb) | Extract a monolayer from a layered material. |
| [Create Cluster](other/materials_designer/create_cluster_specific_shape.ipynb) | Create a nanoparticle cluster with a predefined shape. |
| [Create Point Defect](other/materials_designer/create_point_defect.ipynb) | Introduce a vacancy or substitution point defect. |
| [Create Point Defect Pair](other/materials_designer/create_point_defect_pair.ipynb) | Introduce a pair of point defects. |
| [Create Adatom Defect](other/materials_designer/create_adatom_defect.ipynb) | Place an adatom on a surface. |
| [Create Island Defect](other/materials_designer/create_island_defect.ipynb) | Create a surface island defect. |
| [Create Terrace Defect](other/materials_designer/create_terrace_defect.ipynb) | Create a surface terrace defect. |
| [Create Maxwell Disorder](other/materials_designer/create_maxwell_disorder.ipynb) | Introduce Maxwell disorder into a structure. |
| [Create Perturbation](other/materials_designer/create_perturbation.ipynb) | Apply atomic perturbations. |
| [Create Cutout](other/materials_designer/create_cutout_box.ipynb) | Cut out a box-shaped region from a structure. |
| [Optimize Film Position](other/materials_designer/optimize_film_position.ipynb) | Optimize the vertical position of a film on a substrate. |
| [Passivate Slab](other/materials_designer/passivate_slab.ipynb) | Add passivation atoms to slab surfaces. |
| [Passivate Edge](other/materials_designer/passivate_edge.ipynb) | Passivate nanoribbon or nanowire edges. |
| [Import from Files](other/materials_designer/import_materials_from_files.ipynb) | Import structures from local files (CIF, POSCAR, …). |
| [Import from JARVIS DB](other/materials_designer/import_material_from_jarvis_db_entry.ipynb) | Import a structure from the JARVIS database. |
| [Import from Standata](other/materials_designer/import_materials_from_standata.ipynb) | Import structures from the Standata library. |
| [Custom Transformation](other/materials_designer/custom_transformation.ipynb) | Apply a user-defined transformation to a structure. |
| [Under the Hood](other/materials_designer/under_the_hood.ipynb) | Internals: how Materials Designer notebooks communicate with the platform. |

### Simulation Workflows (`other/materials_designer/workflows/`)

Workflow notebooks that run simulations.

| Notebook | Description |
|----------|-------------|
| [Introduction](other/materials_designer/workflows/Introduction.ipynb) | Overview of the workflow notebook environment. |
| [Total Energy](other/materials_designer/workflows/total_energy.ipynb) | Calculate the total DFT energy of a material. |
| [Total Energy Convergence](other/materials_designer/workflows/total_energy_convergence.ipynb) | Converge total energy with respect to k-points and cutoff. |
| [Total Energy Post-Processing](other/materials_designer/workflows/total_energy_post_processing.ipynb) | Post-process total energy results. |
| [Relaxation](other/materials_designer/workflows/relaxation.ipynb) | Relax atomic positions and/or cell parameters. |
| [Equation of State](other/materials_designer/workflows/equation_of_state.ipynb) | Compute the equation of state (energy vs. volume). |
| [Band Gap](other/materials_designer/workflows/band_gap.ipynb) | Calculate the electronic band gap. |
| [Band Structure](other/materials_designer/workflows/band_structure.ipynb) | Compute and plot the electronic band structure. |
| [Band Structure (HSE)](other/materials_designer/workflows/band_structure_hse.ipynb) | Band structure with the HSE hybrid functional. |
| [Convergence](other/materials_designer/workflows/convergence.ipynb) | General convergence study. |
| [Surface Energy](other/materials_designer/workflows/surface_energy.ipynb) | Calculate surface formation energy. |
| [Interfacial Energy](other/materials_designer/workflows/interfacial_energy.ipynb) | Calculate interfacial energy γ at a heterostructure. |
| [Valence Band Offset](other/materials_designer/workflows/valence_band_offset.ipynb) | Determine the valence band offset at an interface. |

### `notebooks_utils` — Python Utility Package

`src/py/mat3ra/notebooks_utils` is the shared Python library used by all notebooks. It is organised in four layers:

```
primitive/  →  core/  →  ipython/  →  pyodide/
```

| Layer | Location | Purpose |
|-------|----------|---------|
| `primitive` | `notebooks_utils/primitive/` | Pure stdlib: enums, environment detection, logger, CLI helpers. No third-party dependencies. |
| `core` | `notebooks_utils/core/` | Third-party packages (`mat3ra.api_client`, `requests`, `numpy`, …). No IPython or browser APIs. Organised by domain under `core/entity/<domain>/` with separate `api.py`, `io.py`, and `analysis.py` files. |
| `ipython` | `notebooks_utils/ipython/` | IPython/ipywidgets display helpers, HTML/JS output, and domain-specific plots. Works in JupyterLab, Colab, and VS Code notebooks. |
| `pyodide` | `notebooks_utils/pyodide/` | JupyterLite-specific overrides: `micropip` installation, `pyfetch` HTTP, `BroadcastChannel` data bridge, and WASM/Emscripten APIs. |

Top-level files (`auth.py`, `io.py`, `ui.py`, `plot.py`, `settings.py`, `material.py`, `job.py`) are thin routing adapters that keep notebook code environment-agnostic.

See [`src/py/mat3ra/notebooks_utils/README.md`](src/py/mat3ra/notebooks_utils/README.md) for the full developer guide.



## Setup

NOTE: this package targets **Python 3.10 or newer** (`requires-python` in `pyproject.toml`). Use [`pyenv`](https://github.com/pyenv/pyenv#installation) to manage Python versions.

Follow the steps below in order to setup and view the Jupyter notebooks:

0. [Install git-lfs](https://help.github.com/articles/installing-git-large-file-storage/) [[3](#links)] in order to get access to the source code and notebook files.

1. Clone repository:

    ```bash
    git clone https://github.com/Exabyte-io/api-examples.git
    ```

    Or, if you have set up SSH keys

    ```bash
    git clone git@github.com:Exabyte-io/api-examples.git
    ```

    In case for some reason git-lfs was not installed at the time of cloning, the files can be pulled after installing git-lfs, through `git lfs pull`.

    Related to this, please be aware that as the `.ipynb` and `.poscar` files are stored on git-lfs, they are not part of the zip archive downloaded through GitHub's web interface.

2. Create a virtual environment and activate it:

    ```bash
    cd api-examples
    python -m venv .venv
    source .venv/bin/activate
    ```

3. Install the package with the extras that match what you want to run:

    | Use case | Install command |
    |----------|-----------------|
    | API examples (`examples/`) | `pip install -e ".[api,jupyterlab]"` |
    | Materials Designer notebooks (`other/materials_designer/`) | `pip install -e ".[materials,jupyterlab]"` |
    | Workflow notebooks (`other/materials_designer/workflows/`) | `pip install -e ".[workflows,jupyterlab]"` |
    | Everything | `pip install -e ".[all,jupyterlab]"` |
    | Development (linting, tests) | `pip install -e ".[all_dev,jupyterlab]"` |

4. Run Jupyter and open a notebook in a browser. In order for the post-save hook feature to work properly, one must launch their Jupyter Notebook environment in the folder that contains the file `config.py`, which is the `examples` folder shown below:

    ```bash
    cd examples
    jupyter lab --config=config.py
    ```

## Usage

In order to run or edit the examples:

1. Assert an existing Mat3ra.com account. Examples require an account to run. New users can register [here](https://platform.mat3ra.com/register) to obtain one.

2. Open the desired example notebook and run all cells. Authentication uses OIDC device flow via `await authenticate()` — a browser popup opens for login. On JupyterLite (platform-embedded notebooks), credentials are injected automatically.

3. Optionally, for local Jupyter without OIDC, set legacy API token values in [settings.json](src/py/mat3ra/notebooks_utils/core/api/settings.json). See [Get Authentication Params](examples/system/get_authentication_params.ipynb) for details. API tokens can also be generated in [Account Preferences](https://docs.mat3ra.com/accounts/ui/preferences/api/) on the platform.

NOTE: The Materials Project API key should be set in `settings.json` and obtained from [https://legacy.materialsproject.org/open](https://legacy.materialsproject.org/open).


## Contribute

This is an open-source repository and we welcome contributions for other use cases. The original set of examples is only meant to demonstrate the capabilities and can be extended.

We suggest forking this repository and introducing the adjustments there. The changes in the fork can further be considered for merging into this repository as it is commonly used on GitHub. This process is explained in more details elsewhere online [[4](#links)].

If you would like to add new examples or adjust existing ones, please consider the following:

1. Put examples into the corresponding directories by domain.

2. Walk the readers through the examples by providing step-by-step explanation similar to [this](examples/material/get_materials_by_formula.ipynb) example.

3. We use post-save hooks to automatically convert notebooks to python scripts. See [config](examples/config.py) file for more information. In order to facilitate code review, we exclude notebook sources in the `other/` directory from version control and store them in Git LFS [[3](#links)]. Please follow this convention.

4. Apply code formatting by installing development requirements as follows:

    ```bash
    pip install -e ."[dev]"
    pre-commit install
    pre-commit run --all-files
    ```

    Check more details about `pre-commit` [here](https://pre-commit.com/).

## Development

To run NBs locally with JupyterLite use `https://github.com/Exabyte-io/jupyterlite` repo to build and run the server.


For local API development with WebApp set the variables in the first cell of the notebooks as follows:

```python
API_HOST = "localhost"
API_PORT = "3000"
API_SECURE = "false"
API_VERSION = "2018-10-01"
```


## Links

1. Mat3ra.com RESTful API, description in the online documentation: [link](https://docs.mat3ra.com/rest-api/overview/)
2. Jupyter.org, official website: [link](https://jupyter.org/)
3. Git Large File Storage, official website: [link](https://git-lfs.github.com/)
4. GitHub Standard Fork & Pull Request Workflow, online explanation: [link](https://gist.github.com/Chaser324/ce0505fbed06b947d962)
