# pyepwmorph

A Python package for accessing global climate models and morphing EnergyPlus Weather (EPW) files with future climate projections from CMIP6 models.

## 🌡️ Overview

`pyepwmorph` enables building performance analysts and researchers to create future weather files by morphing existing EPW files with climate change projections. The package automatically downloads climate model data from Google Cloud and applies scientifically-validated morphing procedures to generate future weather files for building energy simulations.

## ✨ Features

- **Automated Climate Data Access**: Downloads CMIP6 climate model data from Google Cloud Storage
- **Multiple Climate Scenarios**: Supports 4 different Representative Concentration Pathways (RCPs) and Shared Socioeconomic Pathways (SSPs)
- **Intelligent Caching**: Built-in caching system to improve performance and reduce download times
- **Morphing Procedures**: Implements established morphing methodologies for temperature, humidity, wind, solar radiation, and other weather variables
- **Multiple Models**: Access to 50+ global climate models for robust projections
- **Easy-to-Use API**: Simple Python interface for weather file generation

## 🚀 Installation

```bash
pip install pyepwmorph
```

### Development Installation

For development or to access the latest features:

```bash
# Clone the repository
git clone https://github.com/justinfmccarty/pyepwmorph.git
cd pyepwmorph

# Create conda environment (recommended)
conda env create -f environment.yml
conda activate pyepwmorph

# Or install in development mode
pip install -e ".[dev]"
```

## 🌍 Climate Scenarios

The package supports four main climate scenarios based on CMIP6 projections:

### Available Scenarios

| Scenario | Full Name | Description | Expected Warming |
|----------|-----------|-------------|------------------|
| **ssp126** | Best Case Scenario | Strong mitigation, renewable transition | 1.8°C by 2100 |
| **ssp245** | Middle of the Road | Moderate mitigation efforts | 2.7°C by 2100 |
| **ssp370** | Upper Middle Scenario | Regional rivalry, slow convergence | 3.6°C by 2100 |
| **ssp585** | Worst Case Scenario | Fossil-fueled development | 4.4°C by 2100 |

### Percentiles

For each scenario, you can access different percentiles representing uncertainty ranges:

- **1st percentile**: Lower bound of projections (cooler outcomes)
- **50th percentile**: Median projection (most likely outcome)  
- **99th percentile**: Upper bound of projections (warmer outcomes)

## 📊 Morphing Variables

The package can morph the following weather variables:

- **Temperature**: Dry bulb temperature, daily min/max temperatures
- **Humidity**: Relative humidity, absolute humidity, dew point
- **Pressure**: Atmospheric pressure
- **Wind**: Wind speed and direction
- **Clouds and Radiation**: Cloud cover, solar radiation (direct and diffuse)

## 💾 Caching System

`pyepwmorph` includes an intelligent caching system to improve performance:

### Automatic Caching

- Climate model data is automatically cached locally
- Coordinate data for specific locations is cached
- Reduces download time for repeated analyses

### Cache Management Commands

```python
import pyepwmorph.models.access as access

# Get cache statistics
stats = access.get_cmip6_cache_stats()
print(f"Cache size: {stats['total_size_mb']} MB")
print(f"Files cached: {stats['total_files']}")

# Clear cache (useful for development or disk space management)
access.clear_cmip6_cache()
```

### Cache Configuration

- Default cache location: `~/.pyepwmorph_cache/`
- Automatic cleanup when cache exceeds size limits
- Thread-safe caching for concurrent operations

## 🏗️ Quick Start

### Basic Usage

```python
import pyepwmorph.tools.workflow as workflow

# Define morphing parameters
project_name = "MyBuilding_Future"
epw_file = "path/to/your/weather_file.epw"
user_variables = ['Temperature', 'Humidity', 'Clouds and Radiation']
user_pathways = ['Middle of the Road']  # ssp245
percentiles = [50]  # median projection
future_years = [2050]
output_directory = "path/to/output/"

# Run morphing workflow
results = workflow.morphing_workflow(
    project_name=project_name,
    epw_file=epw_file,
    user_variables=user_variables,
    user_pathways=user_pathways,
    percentiles=percentiles,
    future_years=future_years,
    output_directory=output_directory
)
```

### Advanced Configuration

```python
# Use specific climate models (optional)
model_sources = ['ACCESS-CM2', 'CanESM5', 'MIROC6']

# Custom baseline period (default: 1995-2014)
baseline_range = [1990, 2019]

# Multiple scenarios and percentiles
user_pathways = ['Best Case Scenario', 'Middle of the Road', 'Worst Case Scenario']
percentiles = [1, 50, 99]
future_years = [2030, 2050, 2070]

results = workflow.morphing_workflow(
    project_name="ComprehensiveAnalysis",
    epw_file=epw_file,
    user_variables=['Temperature', 'Humidity', 'Pressure', 'Wind', 'Clouds and Radiation'],
    user_pathways=user_pathways,
    percentiles=percentiles,
    future_years=future_years,
    output_directory=output_directory,
    model_sources=model_sources,
    baseline_range=baseline_range
)
```

## 🔬 Available Climate Models

The package provides access to 50+ CMIP6 models. To see available models:

```python
from pyepwmorph.tools.utilities import available_models

# Get list of models available for all scenarios
models = available_models()
print(f"Available models: {len(models)}")
```

## 🛠️ Development & Contributing

### Development Environment Setup

```bash
# Clone and setup development environment
git clone https://github.com/justinfmccarty/pyepwmorph.git
cd pyepwmorph

# Create conda environment
conda env create -f environment.yml
conda activate pyepwmorph

# Install in development mode
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=pyepwmorph

# Run specific test file
pytest tests/test_pyepwmorph.py -v
```

### Code Quality

```bash
# Format code
black pyepwmorph/
isort pyepwmorph/

# Lint code
flake8 pyepwmorph/
```

## 🚀 Making New Releases

For maintainers, the package uses an automated release system:

### Quick Release

```bash
# Patch release (1.0.3 → 1.0.4)
./release.sh patch

# Minor release (1.0.3 → 1.1.0)  
./release.sh minor

# Major release (1.0.3 → 2.0.0)
./release.sh major
```

### What the Release Script Does

1. ✅ **Git Status Check**: Ensures working directory is clean
2. ✅ **Run Tests**: Validates code quality
3. ✅ **Version Bump**: Automatically calculates and updates version numbers
4. ✅ **Build Package**: Creates wheel and source distributions
5. ✅ **Git Operations**: Commits changes, creates tags, pushes to GitHub
6. ✅ **GitHub Integration**: Ready for GitHub release creation

### Manual Release Process

1. **Update version**: The release script handles this automatically
2. **Create GitHub Release**: Visit the provided URL after running `./release.sh`
3. **PyPI Publishing**: Automatic via GitHub Actions when release is created

### Release Workflow

```bash
# Example: Creating a minor release
./release.sh minor

# Output will show:
# ✅ Released version 1.1.0  
# Create a GitHub release at: https://github.com/justinfmccarty/pyepwmorph/releases/new?tag=v1.1.0
```

## 📚 Documentation

### API Reference

The main workflow function provides comprehensive climate morphing:

```python
workflow.morphing_workflow(
    project_name,          # str: Name for your project
    epw_file,              # str: Path to input EPW file
    user_variables,        # list: Variables to morph
    user_pathways,         # list: Climate scenarios
    percentiles,           # list: Percentile projections (1, 50, 99)
    future_years,          # list: Target years for projections
    output_directory,      # str: Where to save morphed files
    model_sources=None,    # list: Specific models (optional)
    baseline_range=None,   # list: Custom baseline period (optional)
    write_file=True        # bool: Whether to write EPW files
)
```

### Variable Dependencies

Some variables have automatic dependencies:

- **Humidity** requires Temperature and Pressure
- **Dew Point** requires Temperature and Humidity

The package automatically adds missing dependencies and notifies you.

## ⚠️ Requirements

- **Python**: 3.10 or higher
- **Operating System**: Windows, macOS, Linux
- **Internet Connection**: Required for downloading climate data
- **Disk Space**: ~50MB for typical cache (varies by usage)

## 📄 License

This project is licensed under the GNU General Public License v3.0 or later (GPL-3.0-or-later). See the [LICENSE](LICENSE) file for details.

## 🤝 Support

- **Issues**: [GitHub Issues](https://github.com/justinfmccarty/pyepwmorph/issues)
- **Documentation**: This README and inline code documentation
- **Examples**: See `examples/` directory for Jupyter notebooks

## 📈 Citation

If you use this package in research, please cite:

```text
McCarty, J. (2025). pyepwmorph: A Python package for climate-informed building performance analysis. 
Version 1.0.3. https://github.com/justinfmccarty/pyepwmorph
```

---

**🌟 Star this repository if you find it useful!**
