# Example of using Mattergen to generate a material

## 1. Installation and setup

### 1.0. Clone the repository

```bash
git clone https://github.com/Exabyte-io/mattergen.git && cd mattergen
```

### 1.1. Create virtual environment

```bash
pyenv local 3.10.12
python -m venv .venv-3.10.12
source .venv-3.10.12/bin/activate
```

### 1.2. Install the package

Try this approach first:

```bash
pip install -e .
```

In case of issues, try using `uv`:

```bash
pip install uv
uv pip install -e .
```

### 1.3. Fix torch compatibility

In case of compatibility issues with torch and torch-scatter, you can try to reinstall specific versions.

Below are the directives for Apple Silicon, 12.6 OSX:

```bash
pip install --no-cache-dir --force-reinstall "torch==2.4.1"
```

In case `torch-scatter` installation fails, try:
```bash
pip install --no-cache-dir --force-reinstall  torch-scatter -f https://data.pyg.org/whl/torch-2.4.1.html
```

### 1.4. Set environment variables

For Apple Silicon devices (M-series chips) set fallback to CPU:
```bash
export MATTERGEN_DEVICE=cpu
export PYTORCH_ENABLE_MPS_FALLBACK=1;
```

## 2.0. Run example

Set model name and results path:
```bash
export MODEL_NAME=chemical_system_energy_above_hull
export RESULTS_PATH="results/$MODEL_NAME/"
```

Run generation:
```bash
mattergen-generate $RESULTS_PATH --pretrained-name=$MODEL_NAME --batch_size=1 --properties_to_condition_on="{'chemical_system': 'Si-O'}" --diffusion_guidance_factor=2.0
```

## 3.0. Results

File structure expected to be like:
```
results
  chemical_system_energy_above_hull
    generated_crystals.extxyz
    generated_crystals_cif.zip
    generated_trajectories.zip
```

Example structural output:
```
8
Lattice="4.810662746429443 0.0 2.003615617752075 2.0573911375230405 4.4635489819590255 1.6285755634307861 0.0 0.0 6.223104953765869" Properties=species:S:1:pos:R:3 pbc="T T T"
Si       3.19007697       0.64344807       2.15220843
O        6.29417322       4.25980285       4.64711970
Si       2.52538380       3.42031925       3.52259767
O        6.28716089       4.28023109       7.76082322
O        3.88651095       4.26880406       3.65002186
O        2.86109621       2.03830726       2.83004283
O        1.84533000       3.12136774       5.01444792
O        3.87107245       0.94328279       6.87403968
```

## 4.0. Run relaxation (optional)

To relax the generated structures, you can use the [Relaxation Notebook](../mtrsm/relax_generated_material.ipynb).

Copy the generated `extxyz` file to the `mtrsm/data/` folder and run the notebook.
