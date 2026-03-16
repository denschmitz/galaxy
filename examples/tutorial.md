# Tutorial Run

This tutorial uses the Pillars of Creation example configuration and is written for Windows 11 PowerShell with Python 3.12.

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
python -m galaxy.cli validate-config --config examples/pillars.yaml
```

## 3. Run the full pipeline

This example is intentionally narrow: it targets a modest crop of the Pillars of Creation with HST narrowband filters so the archive query stays practical.

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli run --config examples/pillars.yaml --workdir artifacts/pillars
```

Expected artifacts:

- `artifacts/pillars/cache/`
- `artifacts/pillars/manifest.json`
- `artifacts/pillars/reprojected/`
- `artifacts/pillars/exported_planes.fits`
- `artifacts/pillars/composite.png`
- `artifacts/pillars/composite.tiff`
- `artifacts/pillars/provenance.json`
- `artifacts/pillars/run_config.yaml`

## 4. Tune interactively

`src/galaxy/ui.py` is the Streamlit UI entrypoint, not the main CLI entrypoint.

```powershell
$env:PYTHONPATH = "src"
python -m streamlit run src/galaxy/ui.py -- artifacts/pillars/exported_planes.fits
```

Use the sidebar controls to toggle planes, adjust RGB weights, change percentiles, and save or load a reusable style file.

## 5. Reproduce the result

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli reproduce --config artifacts/pillars/run_config.yaml --workdir artifacts/pillars
```

## 6. Optional installed console scripts

After `python -m pip install -e .`, setuptools should also create these shortcuts:

```powershell
galaxy validate-config --config examples/pillars.yaml
galaxy run --config examples/pillars.yaml --workdir artifacts/pillars
galaxy reproduce --config artifacts/pillars/run_config.yaml --workdir artifacts/pillars
```

If those scripts are not on `PATH`, keep using the `python -m galaxy.cli ...` form above.
