# pyepwmorph

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.0.0-green.svg)](https://github.com/justinfmccarty/pyepwmorph)

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

## Climate scenarios

| Scenario | SSP | Description | Expected warming |
|----------|-----|-------------|------------------|
| Best Case Scenario | ssp126 | Strong mitigation, renewable transition | ~1.8 C by 2100 |
| Middle of the Road | ssp245 | Moderate mitigation efforts | ~2.7 C by 2100 |
| Upper Middle Scenario | ssp370 | Regional rivalry, slow convergence | ~3.6 C by 2100 |
| Worst Case Scenario | ssp585 | Fossil-fueled development | ~4.4 C by 2100 |

## Morphing variables

- **Temperature** -- dry bulb temperature (shift + stretch)
- **Humidity** -- relative humidity via specific humidity (stretch)
- **Pressure** -- atmospheric pressure (shift)
- **Wind** -- wind speed (stretch)
- **Clouds and Radiation** -- global/diffuse/direct radiation and sky cover
- **Dew Point** -- recalculated from morphed temperature and humidity

### Variable dependencies

Some variables are automatically added when needed:

- **Humidity** requires Temperature and Pressure
- **Dew Point** requires Temperature, Humidity, and Pressure

## Caching

Climate model data is cached locally after the first download to speed up repeated analyses.

```python
import pyepwmorph.models.access as access

stats = access.get_cmip6_cache_stats()
access.clear_cmip6_cache()
```

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

# Run tests
pytest

# Run with coverage
pytest --cov=pyepwmorph
```

## Breaking changes in v2.0.0

- **License changed** from GPL-3.0 to MIT.
- **`future_years`** parameter renamed to **`target_years`** across the API.
  The old name is still accepted with a deprecation warning.
- **`MorphConfig`** accepts new parameters: `data_source`, `custom_data`,
  `reference_scenario`, and `target_years`.
- **EPW I/O** (`pyepwmorph.tools.io`) rewritten with stricter validation.
  Files that are not exactly 8760 data rows will now raise `ValueError`.
  The lat/lon parsing bug in the standalone `epw_location()` function has
  been fixed.
- **`coordinate_cmip6_data`** now accepts an optional `time_slices` dict
  for custom temporal bounds instead of hardcoded 1960-2014 / 2015-2100.
- **Removed** `requirements.txt`, `environment.yml`, `.bumpversion.cfg`.
  Use `uv sync` or `pip install .` instead.
- **Per-module `__version__`** strings removed. Use
  `pyepwmorph.__version__` or `importlib.metadata.version("pyepwmorph")`.

## Requirements

- Python >= 3.9
- Internet connection (for CMIP6 data download)

## License

MIT License. See [LICENSE](LICENSE).

## Citation

```text
McCarty, J. (2026). pyepwmorph: A Python package for climate-informed
EPW file morphing. Version 2.0.0.
https://github.com/justinfmccarty/pyepwmorph
```
