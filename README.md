# pyepwmorph

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/pyepwmorph.svg)](https://pypi.org/project/pyepwmorph/)

A Python package for morphing EnergyPlus Weather (EPW) files with climate model data. Supports CMIP6 projections from Google Cloud and custom CSV-based model data for both future and historical scenarios.

## Overview

`pyepwmorph` enables building performance analysts and researchers to create morphed weather files by applying scientifically validated procedures (Belcher et al. 2005, Jentsch et al. 2013) to existing EPW files. The package can morph EPWs using:

- **CMIP6 data** fetched automatically from Google Cloud (Pangeo)
- **Custom CSV data** from any climate model, including historical reconstructions

## Installation

### With uv (recommended)

```bash
uv add pyepwmorph
```

### Development setup

```bash
git clone https://github.com/justinfmccarty/pyepwmorph.git
cd pyepwmorph
uv sync --extra dev
```

### With pip

```bash
pip install pyepwmorph
```

## Quick start

### CMIP6 workflow (future projections)

```python
import pyepwmorph.tools.workflow as workflow

results = workflow.morphing_workflow(
    project_name="MyBuilding_Future",
    epw_file="weather.epw",
    user_variables=["Temperature", "Humidity", "Clouds and Radiation"],
    user_pathways=["Middle of the Road"],   # ssp245
    percentiles=[50],
    target_years=[2050],
    output_directory="output/",
)
```

### Custom CSV workflow (historical or any model)

```python
import pyepwmorph.tools.workflow as workflow

custom_data = {
    "reference": {
        "tas": "data/reference_tas.csv",
        "tasmax": "data/reference_tasmax.csv",
        "tasmin": "data/reference_tasmin.csv",
    },
    "target_1990s": {
        "tas": "data/target_tas.csv",
        "tasmax": "data/target_tasmax.csv",
        "tasmin": "data/target_tasmin.csv",
    },
}

results = workflow.morphing_workflow(
    project_name="Historical_Morph",
    epw_file="weather.epw",
    user_variables=["Temperature"],
    user_pathways=["target_1990s"],
    percentiles=[50],
    target_years=[1990],
    output_directory="output/",
    data_source="custom",
    custom_data=custom_data,
    reference_scenario="reference",
)
```

Custom CSVs should have a `date` column (parseable by pandas) and a column named after the CMIP6 variable (e.g. `tas`, `tasmax`). Rows should be monthly.

The reference and target scenarios must cover **different years**, the same way the CMIP6 `historical` and `sspXXX` experiments do. The two series are concatenated before the baseline and target periods are sliced out, so overlapping years get averaged together and weaken the climate signal. Keep `baseline_range` inside the years the reference scenario covers.

## Climate scenarios

| Scenario              | SSP    | Description                             | Expected warming |
| --------------------- | ------ | --------------------------------------- | ---------------- |
| Best Case Scenario    | ssp126 | Strong mitigation, renewable transition | ~1.8 C by 2100   |
| Middle of the Road    | ssp245 | Moderate mitigation efforts             | ~2.7 C by 2100   |
| Upper Middle Scenario | ssp370 | Regional rivalry, slow convergence      | ~3.6 C by 2100   |
| Worst Case Scenario   | ssp585 | Fossil-fueled development               | ~4.4 C by 2100   |

## Morphing variables

- **Temperature** -- dry bulb temperature (shift + stretch)
- **Humidity** -- relative humidity, stretched in specific humidity space
- **Pressure** -- atmospheric pressure (shift)
- **Wind** -- wind speed (stretch)
- **Clouds and Radiation** -- global/diffuse/direct radiation and sky cover
- **Dew Point** -- recalculated from morphed temperature and humidity

### Variable dependencies

Some variables cannot be morphed on their own:

- **Humidity** requires Temperature and Pressure
- **Dew Point** requires Temperature, Humidity, and Pressure

Dependencies are added automatically and are **written to the output file**. Asking for `Dew Point` alone therefore returns an EPW with morphed pressure, temperature, relative humidity, and dew point, which keeps the file internally consistent. `MorphConfig.resolved_variables` shows exactly what will be written, in the order it is computed.

## Caching

Climate model data is cached locally after the first download, and the cache is consulted before the remote catalogue is opened so a hit costs no network traffic.

```python
import pyepwmorph.models.access as access

stats = access.get_cmip6_cache_stats()
access.clear_cmip6_cache()
```

Cache entries live in the per-user cache directory (`~/Library/Caches/pyepwmorph` on macOS, `~/.cache/pyepwmorph` on Linux, `%LOCALAPPDATA%\pyepwmorph` on Windows) and are keyed by location, pathway, variable, model sources, and time slices. Two environment variables override the defaults:

| Variable                  | Purpose                        | Default |
| ------------------------- | ------------------------------ | ------- |
| `PYEPWMORPH_CACHE_DIR`    | Where cache files are written  | per-user cache directory |
| `PYEPWMORPH_CACHE_MAX_MB` | Size cap before old files go   | 500 |

## Available climate models

```python
from pyepwmorph.tools.utilities import available_models

models = available_models()
```

## Development

```bash
git clone https://github.com/justinfmccarty/pyepwmorph.git
cd pyepwmorph
uv sync --extra dev

# Run tests (fully offline)
uv run pytest

# Run with coverage
uv run pytest --cov=pyepwmorph

# Lint
uv run ruff check pyepwmorph tests gui
```

### Releases

```bash
./release.sh [patch|minor|major]
```

The script refuses to run on a dirty tree, off `main`, with failing lint or tests, or without a matching `CHANGELOG.md` section. It bumps the version, tags, and pushes; creating the GitHub Release then triggers the PyPI publish workflow.

```bash
gh release create v3.0.0 \
  --title "v3.0.0" \
  --notes "See CHANGELOG.md."
```

## Changes

See [CHANGELOG.md](CHANGELOG.md) for the full history. The most recent release corrects several morphing calculations, so morphed humidity, dew point, wind speed, cloud cover, and direct/diffuse radiation all differ from files produced by earlier versions.

## Requirements

- Python >= 3.9
- pandas >= 2.2
- Internet connection (for CMIP6 data download; the custom CSV workflow runs offline)

## License

MIT License. See [LICENSE](LICENSE).

## Citation

```text
McCarty, J. (2026). pyepwmorph: A Python package for climate-informed
EPW file morphing. Version 3.0.0.
https://github.com/justinfmccarty/pyepwmorph
```
