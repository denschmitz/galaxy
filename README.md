# Galaxy

Galaxy is a Python project for building presentation-quality multi-band composite images from publicly available Hubble Space Telescope (HST) and James Webb Space Telescope (JWST) imaging data.

The pipeline is intentionally split between:

- science-calibrated source products cached exactly as downloaded
- presentation processing products such as reprojection, optional deconvolution, color mapping, and nonlinear stretches

This repository implements the P0 pipeline end to end and includes extension points for the P1 UI and PSF work.

## Entry points

Galaxy has two different entry modules:

- CLI pipeline: `python -m galaxy.cli ...`
- Streamlit preview UI: `python -m streamlit run src/galaxy/ui.py -- ...`

`src/galaxy/ui.py` is not the main module for the project. It is only the interactive preview UI entrypoint.

If you install the project with `pip install -e .`, setuptools will also create console scripts such as `galaxy` and `galaxy-ui`. The documentation below uses `python -m ...` so it works directly from a fresh checkout on Windows 11 with Python 3.12.

## Presentation-product notice

Galaxy produces presentation products. Nonlinear stretches, channel weighting, derived planes, saturation controls, and any optional deconvolution are non-photometric operations intended for visual communication rather than quantitative science analysis.

## Features

- Target selection by common name or explicit coordinates
- MAST search and deterministic product selection for HST and JWST imaging products
- Local cache with manifest and checksum tracking
- FITS ingestion with WCS-aware reprojection onto a user-defined canvas
- Multi-plane export, RGB composition, PNG/TIFF export, and provenance reporting
- Canonical YAML configuration for non-interactive execution and reproduction
- Streamlit preview UI for tuning mappings and tone settings without re-downloading data

## Installation on Windows 11 with Python 3.12

From `C:\Data\dev\galaxy`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
$env:PYTHONPATH = "src"
```

Notes:

- `python -m pip install -e .` is optional if you only want to run via `python -m galaxy.cli` with `PYTHONPATH=src`.
- If PowerShell blocks activation scripts, run `Set-ExecutionPolicy -Scope Process RemoteSigned` in the same shell first.

## Quick start

1. Review [`examples/orion.yaml`](/C:/Data/dev/galaxy/examples/orion.yaml).
2. Validate the configuration:

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli validate-config --config examples/orion.yaml
```

3. Run the download and compose pipeline:

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli run --config examples/orion.yaml --workdir artifacts/orion
```

4. Reproduce the same output later from the saved config and local cache:

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli reproduce --config artifacts/orion/run_config.yaml --workdir artifacts/orion
```

5. Launch the preview UI against the aligned plane export:

```powershell
$env:PYTHONPATH = "src"
python -m streamlit run src/galaxy/ui.py -- artifacts/orion/exported_planes.fits
```

## CLI overview

Repo-local invocation:

```powershell
python -m galaxy.cli run --config CONFIG.yaml --workdir OUTPUT_DIR
python -m galaxy.cli run --config CONFIG.yaml --workdir OUTPUT_DIR --mode download-only
python -m galaxy.cli run --config CONFIG.yaml --workdir OUTPUT_DIR --mode reproject-only
python -m galaxy.cli run --config CONFIG.yaml --workdir OUTPUT_DIR --mode compose-only
python -m galaxy.cli reproduce --config CONFIG.yaml --workdir OUTPUT_DIR
python -m galaxy.cli validate-config --config CONFIG.yaml
```

After editable install, these equivalent console scripts should also work:

```powershell
galaxy run --config CONFIG.yaml --workdir OUTPUT_DIR
galaxy reproduce --config CONFIG.yaml --workdir OUTPUT_DIR
galaxy validate-config --config CONFIG.yaml
```

Target override flags are supported for automation:

```powershell
python -m galaxy.cli run --config CONFIG.yaml --target-name "Orion Nebula" --radius-arcmin 12 --workdir OUTPUT_DIR
python -m galaxy.cli run --config CONFIG.yaml --ra 83.82208 --dec -5.39111 --box-arcmin 20 20 --workdir OUTPUT_DIR
```

## UI overview

The Streamlit preview UI supports:

- plane enable/disable toggles
- per-plane weights into R/G/B
- channel stretch selection and parameters
- black/white percentile controls
- per-channel gain
- global saturation
- save/load of style mappings

The UI operates on already aligned planes and does not trigger re-downloads.

## Configuration schema

Galaxy uses a single canonical YAML schema defined in [`src/galaxy/config.py`](/C:/Data/dev/galaxy/src/galaxy/config.py). It covers:

- target and region definitions
- archive filters
- output canvas
- plane selection
- mapping and tone settings
- PSF/deconvolution settings
- execution policy and output paths

See [`examples/orion.yaml`](/C:/Data/dev/galaxy/examples/orion.yaml) and [`examples/tutorial.md`](/C:/Data/dev/galaxy/examples/tutorial.md).

## Output artifacts

Each run can produce:

- `cache/` downloaded source FITS files, preserved unmodified
- `manifest.json` deterministic download manifest
- `reprojected/` per-plane aligned FITS files and coverage masks
- `exported_planes.fits` aligned multi-plane FITS export
- `composite.png` and `composite.tiff`
- `provenance.json` full run provenance
- `run_config.yaml` resolved configuration for reproducibility

## Data source and attribution notes

Galaxy searches the [MAST archive](https://mast.stsci.edu/). Users remain responsible for following STScI/MAST data-use guidance and any mission-specific attribution expectations. PSF generation or deconvolution methods introduced later should be documented alongside their own citation and license requirements.

## Development

Syntax check from the repo root:

```powershell
$env:PYTHONPATH = "src"
python -m compileall src tests
```

Run tests after installing dev dependencies:

```powershell
$env:PYTHONPATH = "src"
python -m pytest
```

Key design documentation lives in [`docs/design-requirements.md`](/C:/Data/dev/galaxy/docs/design-requirements.md).
