# Tutorial Run

This tutorial uses JSON scene cards and Windows 11 PowerShell with Python 3.12.

## 1. Install dependencies

From the repository root:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
$env:PYTHONPATH = "src"
~~~

## 2. Validate an example scene card

The translated example is a valid draft. It intentionally does not invent exact MAST
product pins, so it must be refined before pipeline execution.

~~~powershell
python -m galaxy.cli validate-scene --scene examples/pillars.scene.json
~~~

## 3. Open the five-screen UI

Normal launch opens Discovery. The configured scene library defaults to
artifacts/scenes.

~~~powershell
python -m streamlit run src/galaxy/ui.py
~~~

To open the example directly in Scene refinement:

~~~powershell
python -m streamlit run src/galaxy/ui.py -- examples/pillars.scene.json
~~~

Query MAST in Data, inspect and apply exact products, review Color and Frame, then
save the scene card. A command-line override can select another scene library:

~~~powershell
python -m streamlit run src/galaxy/ui.py -- --scene-dir alternate-scenes
~~~

## 4. Run a render-ready saved scene

Use the saved JSON path shown by the UI. A workdir is optional; by default each render
uses a new associated asset directory beside the scene card.

~~~powershell
python -m galaxy.cli run --scene artifacts/scenes/your-scene.scene.json
~~~

Expected successful full-render records and files include candidate and source
manifests, aligned planes, PNG and TIFF composites, provenance, a thumbnail, and
immutable references appended to the scene card.

## 5. Reproduce or open an artifact

~~~powershell
python -m galaxy.cli reproduce --scene artifacts/scenes/your-scene.scene.json
python -m streamlit run src/galaxy/ui.py -- artifacts/scenes/your-scene.scene.json
~~~

The UI also accepts candidate manifest JSON, multi-plane FITS, or a workdir containing
one of the supported artifacts. YAML is not a normal UI or CLI input.
