# Galaxy

Galaxy is a Python project for building presentation-quality multi-band composite images from publicly available Hubble Space Telescope (HST) and James Webb Space Telescope (JWST) imaging data.

The pipeline is intentionally split between:

- science-calibrated source products cached exactly as downloaded
- presentation processing products such as reprojection, optional deconvolution, color mapping, and nonlinear stretches

This repository implements the scene-card pipeline, optional PSF processing, and the
five-screen interactive workflow.

## Entry points


Galaxy has two different entry modules:

- CLI pipeline: `python -m galaxy.cli ...`
- Streamlit UI: `python -m streamlit run src/galaxy/ui.py`

`src/galaxy/ui.py` is the interactive workflow entrypoint; the CLI remains the
automation and direct-execution entrypoint.

If you install the project with `pip install -e .`, setuptools will also create console scripts such as `galaxy` and `galaxy-ui`. The documentation below uses `python -m ...` so it works directly from a fresh checkout on Windows 11 with Python 3.12.

## Presentation-product notice

Galaxy produces presentation products. Nonlinear stretches, channel weighting, derived planes, saturation controls, and any optional deconvolution are non-photometric operations intended for visual communication rather than quantitative science analysis.

## Features

- Target selection by common name or explicit coordinates
- MAST search and deterministic product selection for HST and JWST imaging products
- Local cache with manifest and checksum tracking
- FITS ingestion with WCS-aware reprojection onto a user-defined canvas
- Multi-plane export, RGB composition, PNG/TIFF export, and provenance reporting
- Canonical JSON scene cards with exact selected-product pins and immutable render history
- Streamlit workflow for discovering, selecting, refining, rendering, inspecting artifacts, and saving scenes

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

1. Review `examples/pillars.scene.json` or `examples/s305_offset.scene.json`, then select exact MAST products before rendering.
2. Validate the scene card:

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli validate-scene --scene examples/pillars.scene.json
```

3. Run the download and compose pipeline:

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli run --scene PATH_TO_RENDER_READY_SCENE.scene.json
```

4. Reproduce the same scene revision and exact product selection:

```powershell
$env:PYTHONPATH = "src"
python -m galaxy.cli reproduce --scene PATH_TO_RENDER_READY_SCENE.scene.json
```

5. Launch the UI normally:

```powershell
$env:PYTHONPATH = "src"
python -m streamlit run src/galaxy/ui.py
```

Open **Saved scenes**, select **Pillars of Creation** under **Examples**, and inspect
the **Artifacts** tab. The bundled card is protected: its save action creates a new
user-owned scene under the configured scene directory. This first flow is local and
does not download FITS data.

## CLI overview

Repo-local invocation:

```powershell
python -m galaxy.cli run --scene SCENE.scene.json
python -m galaxy.cli run --scene SCENE.scene.json --mode download-only
python -m galaxy.cli run --scene SCENE.scene.json --mode reproject-only
python -m galaxy.cli run --scene SCENE.scene.json --workdir ASSOCIATED_CHILD --mode compose-only
python -m galaxy.cli reproduce --scene SCENE.scene.json
python -m galaxy.cli validate-scene --scene SCENE.scene.json
```

After editable install, these equivalent console scripts should also work:

```powershell
galaxy run --scene SCENE.scene.json
galaxy reproduce --scene SCENE.scene.json
galaxy validate-scene --scene SCENE.scene.json
```

Change target, framing, or product selection in the scene card and save it before execution. The CLI does not apply ephemeral scene-defining overrides.

## UI overview

The Streamlit five-screen workflow supports:

- name, coordinate, latest-release tracker, and existing-artifact discovery
- exact MAST product selection with explicit recommendation application
- scene framing, RGB mapping, tone adjustment, and branch selection
- background preview generation with safe-boundary cancellation
- independent JSON scene saving and PNG/TIFF export
- saved-scene reopening and unsaved duplication

## Scene-card schema

Galaxy uses the JSON project contract in `docs/scene_card_schema.md` and the machine-readable `docs/scene_card.schema.json`. It covers:

- target and region definitions
- archive filters
- output canvas
- plane selection
- mapping and tone settings
- PSF/deconvolution settings using Richardson-Lucy deconvolution with either a common Gaussian PSF or per-plane kernel FITS files
- execution policy and output paths

Galaxy-owned YAML runtime and temporary translation tooling were retired after the
example translations and JSON consumer cutover were verified. YAML is not accepted by
the UI or CLI.

## Output artifacts

The normative naming and placement contract is
[`docs/artifact_storage_spec.md`](docs/artifact_storage_spec.md). The current
execution layout predates that contract and remains tracked as `GAP-STORAGE-001`;
existing data is not silently migrated. Current runs can produce:

- `cache/` downloaded source FITS files, preserved unmodified
- `manifest.json` deterministic download manifest
- `reprojected/` per-plane aligned FITS files and coverage masks
- `exported_planes.fits` aligned multi-plane FITS export
- `composite.png` and `composite.tiff`
- `provenance.json` full run provenance
- the scene card itself, updated with immutable successful render and asset records

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

Key design documentation lives in
[`docs/design_requirements.md`](docs/design_requirements.md).



