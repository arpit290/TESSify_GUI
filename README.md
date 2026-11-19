# TESSify GUI

TESSify GUI is a PySide6 desktop interface for TESSify projects. It uses the
`TESSify` scientific package to download and process TESS files, review generated
graphs, shortlist candidates, and export results.

## Requirements

- Python 3.10 or newer
- `curl` available on `PATH` for bulk downloads
- `TESSify` 0.6.7 or newer

## Installation

```powershell
python -m pip install TESSify_GUI
```

For a source checkout:

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Launch

After installation:

```powershell
tessify-gui
```

Or run the package as a module:

```powershell
python -m TESSify_GUI
```

## Features

- Create or restore TESSify projects
- Download Light Curve and Target Pixel files
- Process downloaded FITS files into graphs
- Review and shortlist candidates
- Resume interrupted project work
- Export shortlisted TIC IDs

The GUI is separate from the scientific package. Core project behavior comes
from the installed `TESSify` package, whose version must be 0.6.7 or newer.
