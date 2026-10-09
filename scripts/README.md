# Maintenance scripts

Run from the project root using the repository virtual environment.

The one-time YAML migration utility was retired in Phase 5 after the translated JSON
examples and all normal JSON consumers were verified. Add future maintenance scripts
only when they implement a documented requirement.

## Phase 3 background candidate

`phase3_background_candidate.py` applies the normative BG-PED-001 estimator to a
retained aligned-plane asset without modifying the scene or historical render. It
uses the selected render's persisted canvas to recover WCS for pre-Phase-1 legacy
stacks, writes diagnostics and a region overlay, and generates a candidate PNG and
uint16 TIFF with the persisted render mapping/tone recipe.

Run from the project root:

```text
.venv\Scripts\python.exe scripts\phase3_background_candidate.py SCENE_JSON ALIGNED_ASSET_ID --center-x X --center-y Y --width-pixels W --height-pixels H --output-dir OUTPUT_DIR
```

## Phase 4 coverage candidates

`phase4_coverage_candidates.py` compares output-footprint and tone-reference
policies against retained aligned-plane assets without modifying scene cards. The
accepted candidate retains the union of valid pixels and derives the shared tone
transform from the common required-band overlap.

Run the fixed Phase 4 evaluation set from the project root:

```text
.venv\Scripts\python.exe scripts\phase4_coverage_candidates.py --output-root artifacts\phase4-coverage
```

The command writes candidate PNGs and `summary.json` below the output root.

## Phase 5 stretch candidates

`phase5_stretch_candidates.py` compares the persisted legacy recipe with
shared-intensity asinh, the explicit single-main-stretch preset, and a fixed GHS
reference recipe. It also attempts an auto-stretch proposal when the scene has
persisted background regions. Scene cards and retained renders are not modified.

```text
.venv\Scripts\python.exe scripts\phase5_stretch_candidates.py SCENE_JSON [SCENE_JSON ...] --output artifacts\phase5-stretch
```

## Native NaN bridge benchmark

`benchmark_native_bridge.py` measures BRIDGE-MEDIAN-001 native preparation on an
immutable local FITS source. It writes a JSON report containing hardware, effective
profile, counts, load baseline, elapsed time, resident/committed memory and the
native resource gate. It does not invoke pipeline processing or alter source files.

```text
.venv\Scripts\python.exe scripts\benchmark_native_bridge.py --source SOURCE_FITS --output artifacts\reprojection-bridge\native-benchmark.json
```

The budget/metric is defined in [the algorithm](../docs/reprojection_bridge_algorithm.md).
Integrated reprojection, both-branch and UI checks remain separate plan gates.


`benchmark_bridge_integration.py` measures native preparation plus actual
interpolation or adaptive resampling of the full Pillars F090W source into a
512-square specimen canvas. Use project `.venv`, `--source <FITS>`,
`--output <JSON>`, and optionally `--adaptive`. It checks the frozen 120-second
and 16-GiB peak-resident budget and rejects using the source as the report path.
The report retains resident/committed memory, counts, dimensions and elapsed
time. This bounded benchmark does not promise a runtime for arbitrary scenes.
