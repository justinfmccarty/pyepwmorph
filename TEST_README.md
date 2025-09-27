# PyEPWmorph Test Suite

This directory contains comprehensive testing scripts for the PyEPWmorph package, which enables climate projection downscaling for building energy weather files.

## Overview

PyEPWmorph is a Python package that:
- Accesses global climate models (CMIP6) from Google Cloud
- Morphs Typical Meteorological Year (TMY/EPW) weather files
- Applies climate projections to create future weather scenarios
- Supports multiple climate variables and emission pathways

## Test Scripts

### 1. `quick_test.py` - Simple Test Runner

A lightweight test script that validates core functionality without complex dependencies.

**Usage:**
```bash
python quick_test.py
```

**What it tests:**
- ✅ Package imports and module structure
- ✅ EPW file reading and data validation  
- ✅ Configuration object management
- ✅ Basic morphing procedures
- ✅ Utility functions
- ✅ File input/output operations

**Requirements:**
- Requires EPW files in `examples/` or `notebooks/` directories
- Tests run offline (no network access needed)
- Minimal dependencies beyond the package requirements

### 2. `test_pyepwmorph.py` - Comprehensive Test Suite

A full unittest-based test suite with detailed validation and error handling.

**Usage:**
```bash
python test_pyepwmorph.py
```

**What it tests:**
- 🔍 Detailed EPW file structure validation
- 🌍 Climate data access workflow (simulated)
- 🧮 Mathematical morphing procedures
- ⚙️ Configuration validation and error handling
- 📊 Performance benchmarking
- 🔄 Integration workflows
- 📁 File operations and data integrity

## Test Data Requirements

The tests require sample EPW weather files. The package includes:

1. **Examples directory** (`examples/`):
   - `USA_MO_Whiteman.AFB.724467_TMY3.epw` - Missouri weather station
   - Pre-computed results in `results/` subdirectory

2. **Notebooks directory** (`notebooks/`):
   - `USA_PA_Harrisburg.Intl.AP.723990_TMY3.epw` - Pennsylvania weather station
   - Additional test outputs

## Running the Tests

### Prerequisites

1. **Install the package dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Ensure you're in the package root directory** (where `pyepwmorph/` folder exists)

3. **Check that sample EPW files are available:**
   ```bash
   ls examples/*.epw
   ls notebooks/*.epw
   ```

### Quick Test (Recommended)

For a fast validation of core functionality:

```bash
python quick_test.py
```

Expected output:
```
==================================================
PYEPWMORPH QUICK TEST SUITE
==================================================
Testing core functionality of climate projection downscaling package

[1/6] Basic Imports
------------------------------
✓ All core modules imported successfully

[2/6] EPW Reading  
------------------------------
✓ EPW file loaded successfully: USA_MO_Whiteman.AFB.724467_TMY3.epw
  Location: 38.73, -93.55
  Data rows: 8760

[3/6] Configuration
------------------------------
✓ Configuration object created successfully
  Project: test_project
  Model sources: 3 models
  Baseline range: (1991, 2020)

[4/6] Morphing Procedures
------------------------------
✓ Basic morphing procedures work correctly
  Shift test: 20.0 + 2.0 = 22.0
  Stretch test: 20.0 * 1.1 = 22.0

[5/6] Utilities
------------------------------
✓ Utility functions work correctly
  Timestamp length: 8760
  Future period for 2050: (2036, 2065)

[6/6] File Operations
------------------------------
✓ File operations work correctly
  Output file size: 693.2 KB
  Temperature increase: +2.0°C

==================================================
TEST SUMMARY
==================================================
Passed: 6/6
Failed: 0/6

🎉 All tests passed! The package is working correctly.
```

### Comprehensive Test

For detailed testing with performance benchmarks:

```bash
python test_pyepwmorph.py
```

## Understanding the Package Workflow

The tests validate the following typical workflow:

### 1. **EPW File Processing**
```python
from pyepwmorph.tools import io as morph_io

# Load weather file
epw_obj = morph_io.Epw("weather_file.epw")
print(f"Location: {epw_obj.location['latitude']}, {epw_obj.location['longitude']}")
print(f"Baseline period: {epw_obj.detect_baseline_range()}")
```

### 2. **Configuration Setup**
```python
from pyepwmorph.tools import configuration as morph_config

config = morph_config.MorphConfig(
    project_name='my_project',
    epw_fp='weather_file.epw',
    user_variables=['Temperature', 'Humidity', 'Pressure'],
    user_pathways=['Best Case Scenario', 'Middle of the Road', 'Worst Case Scenario'],
    percentiles=[1, 50, 99],
    future_years=[2050, 2070],
    output_directory='results/'
)
```

### 3. **Climate Data Access** (requires network)
```python
from pyepwmorph.models import access, coordinate, assemble

# Access CMIP6 climate models
dataset_dict = access.access_cmip6_data(
    models=['ACCESS-CM2', 'CanESM5', 'TaiESM1'],
    pathway='ssp126',  # Best case scenario
    variable='tas'     # Air temperature
)

# Process and coordinate the data
dataset_dict = coordinate.coordinate_cmip6_data(
    latitude=config.epw.location['latitude'],
    longitude=config.epw.location['longitude'],
    pathway='ssp126',
    variable='tas',
    dataset_dict=dataset_dict
)

# Create ensemble from multiple models
ensemble_data = assemble.build_cmip6_ensemble([50], 'tas', dataset_dict)
```

### 4. **Weather Variable Morphing**
```python
from pyepwmorph.tools import workflow as morph_work

# Complete morphing workflow
results = morph_work.morphing_workflow(
    project_name=config.project_name,
    epw_file=config.epw_fp,
    user_variables=config.user_variables,
    user_pathways=config.user_pathways,
    percentiles=config.percentiles,
    future_years=config.future_years,
    output_directory=config.output_directory
)
```

## Key Climate Variables

The package can morph the following weather variables:

| Variable | Description | Climate Model Variables |
|----------|-------------|------------------------|
| **Temperature** | Dry bulb temperature | `tas`, `tasmax`, `tasmin` |
| **Humidity** | Relative humidity | `huss` (specific humidity) |
| **Pressure** | Atmospheric pressure | `psl` (sea level pressure) |
| **Wind** | Wind speed | `uas`, `vas` (wind components) |
| **Clouds and Radiation** | Solar radiation, cloud cover | `rsds`, `clt` |
| **Dew Point** | Dew point temperature | Derived from temp + humidity |

## Climate Pathways

The package supports these IPCC emission scenarios:

| User Pathway | Model ID | Description |
|--------------|----------|-------------|
| Best Case Scenario | `ssp126` | Low emissions, strong mitigation |
| Middle of the Road | `ssp245` | Moderate emissions |
| Worst Case Scenario | `ssp585` | High emissions, limited mitigation |

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```
   ImportError: No module named 'pyepwmorph'
   ```
   - Ensure you're running from the package root directory
   - Install dependencies: `pip install -r requirements.txt`

2. **No EPW Files Found**
   ```
   FileNotFoundError: No EPW files found for testing
   ```
   - Download sample EPW files to `examples/` directory
   - Check that file extensions are `.epw` (lowercase)

3. **Network Timeout** (for full workflow testing)
   ```
   ConnectionError: Unable to access Google Cloud bucket
   ```
   - Tests are designed to work offline
   - Network tests are simulated to avoid this issue

4. **Memory Issues**
   ```
   MemoryError: Unable to allocate array
   ```
   - Climate data processing can be memory-intensive
   - Reduce the number of models or time periods for testing

### Package Structure Validation

If tests fail, verify the package structure:

```
pyepwmorph/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── access.py
│   ├── assemble.py
│   └── coordinate.py
├── morph/
│   ├── __init__.py
│   └── procedures.py
└── tools/
    ├── __init__.py
    ├── configuration.py
    ├── io.py
    ├── utilities.py
    └── workflow.py
```

### Dependencies

Key dependencies that must be available:
- `pandas` - Data manipulation
- `numpy` - Numerical operations  
- `xarray` - Climate data handling
- `gcsfs` - Google Cloud Storage access
- `intake-esm` - Climate model catalog
- `xclim` - Climate data processing

## Contributing

To add new tests:

1. **For quick tests:** Add functions to `quick_test.py`
2. **For comprehensive tests:** Add test methods to `test_pyepwmorph.py`
3. **Follow the pattern:** Each test should be self-contained and provide clear output

## Performance Notes

- **EPW file reading:** ~0.1-0.5 seconds per file
- **Basic morphing operations:** ~0.001-0.01 seconds for 8760 values
- **Climate data access:** Varies by network speed and data size
- **Full workflow:** 1-10 minutes depending on variables and models

The tests are designed to complete quickly while validating core functionality without requiring large downloads or extended processing time.