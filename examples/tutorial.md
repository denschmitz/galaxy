# Tutorial Run

This tutorial uses the Orion example configuration and is written for Windows 11 PowerShell with Python 3.12.

## 1. Install dependencies

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
$env:PYTHONPATH = "src"
```

If PowerShell blocks activation scripts, run this once in the same shell before activating:

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned
```

## 2. Validate the configuration

This checks that the CLI is alive and that the example YAML passes schema validation:

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli validate-config --config examples/orion.yaml
```

## 3. Run the full pipeline

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli run --config examples/orion.yaml --workdir artifacts/orion
```

Expected artifacts:

- `artifacts/orion/cache/`
- `artifacts/orion/manifest.json`
- `artifacts/orion/reprojected/`
- `artifacts/orion/exported_planes.fits`
- `artifacts/orion/composite.png`
- `artifacts/orion/composite.tiff`
- `artifacts/orion/provenance.json`
- `artifacts/orion/run_config.yaml`

## 4. Tune interactively

`src/galaxy/ui.py` is the Streamlit UI entrypoint, not the main CLI entrypoint.

```powershell
$env:PYTHONPATH = "src"
python -m streamlit run src/galaxy/ui.py -- artifacts/orion/exported_planes.fits
```

Use the sidebar controls to toggle planes, adjust RGB weights, change percentiles, and save a reusable style file.

## 5. Reproduce the result

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli reproduce --config artifacts/orion/run_config.yaml --workdir artifacts/orion
```

## 6. Optional installed console scripts

After `python -m pip install -e .`, setuptools should also create these shortcuts:

```powershell
galaxy validate-config --config examples/orion.yaml
galaxy run --config examples/orion.yaml --workdir artifacts/orion
galaxy reproduce --config artifacts/orion/run_config.yaml --workdir artifacts/orion
```

If those scripts are not on `PATH`, keep using the `python -m galaxy.cli ...` form above.
