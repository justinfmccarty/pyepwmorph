# PyEPWMorph GUI 

Enhanced tkinter-based GUI for EPW file morphing with comprehensive cache management and advanced configuration options. This GUI is more for development


## Features
- **Tabbed Interface**: Separate tabs for EPW Morphing and Cache Management
- **Upper Middle Scenario**: Added SSP3-7.0 climate pathway support
- **Cache Management Tab**: View, monitor, and manage CMIP6 data cache
- **Model Source Selection**: Choose which climate models to use (ACCESS-CM2, CanESM5, TaiESM1)
- **Quick Presets**: One-click presets for conservative and comprehensive analyses
- **Enhanced Variable Info**: Descriptions showing required climate variables for each option
- **Detailed Pathway Info**: Tooltips explaining each SSP scenario
- **Improved Logging**: Better formatted output with status indicators (✓ and ✗)
- **File Counter**: Shows number of generated EPW files after completion


## Running the GUI

### Method 1: Using the launcher script
```bash
python run_gui.py
```

### Method 2: Direct import
```bash
python -m gui.main_window
```

### Method 3: From Python
```python
from gui.main_window import main
main()
```

## Interface Overview

### Tab 1: EPW Morphing

#### Project Configuration
- **Project Name**: Identifier for your morphing project
- **Baseline EPW File**: Upload your present-day EPW file
- **Output Directory**: Where morphed files will be saved

#### Baseline Period
- **Manual Selection**: Use sliders to set start/end years (1950-2020)
- **Auto-Detection**: Check the box to automatically detect from EPW metadata

#### Climate Model Configuration
- **Model Sources**: Select which CMIP6 models to use

- **Climate Pathways**: Choose SSP scenarios
  - **Best Case Scenario** (SSP1-2.6)
  - **Middle of the Road** (SSP2-4.5)
  - **Upper Middle Scenario** (SSP3-7.0)
  - **Worst Case Scenario** (SSP5-8.5)

#### Future Projections
- **Future Years**: Comma-separated list (e.g., `2030,2050,2070,2090`)
- **Percentiles**: Select ensemble percentiles (1st, 5th, 10th, 25th, 50th, 75th, 90th, 95th, 99th)

#### Variables to Morph
Select which climate variables to modify:
- **Temperature**: Dry bulb temperature (requires: tas, tasmax, tasmin)
- **Relative Humidity**: Humidity levels (requires: huss, plus Temperature & Pressure)
- **Wind Speed**: Wind velocity (requires: uas, vas)
- **Clouds & Radiation**: Cloud cover & solar radiation (requires: clt, rsds)
- **Pressure**: Atmospheric pressure (requires: psl)
- **Dew Point**: Dew point temperature (requires: Temperature & Humidity)

*Note: Dependencies are automatically handled - if you select Dew Point, Temperature and Humidity will be included automatically.*

#### Quick Presets
- **Conservative**: Middle pathway, 50th percentile, Temperature only, Year 2050
- **Comprehensive**: All pathways, 1st/50th/99th percentiles, All variables, Years 2050/2070/2090

#### Actions
- **RUN MORPHING**: Start the morphing process
- **RESET ALL**: Clear all selections and return to defaults

### Tab 2: Cache Management *(NEW!)*

#### Cache Overview
- **Cache Directory**: Location of cached files
- **Total Files**: Number of cached entries
- **Total Size**: Current cache size in MB
- **Cache Usage**: Visual progress bar showing usage percentage
- **Max Cache Size**: Size limit (default: 50 MB)

#### Cache Actions
- **Clear Cache**: Remove all cached data (with confirmation)
- **View Cache Location**: Open cache directory in file explorer

#### Cached Files
Detailed listing of all cached files showing:
- Filename
- Size in MB
- Last modified date
- Description (parsed from filename showing location, pathway, variable)

#### About Cache
Information about how the cache works and what it stores.

## Output Files

Morphed EPW files are saved with the naming convention:
```
{future_year}_{pathway}_{percentile}.epw
```

**Pathway Codes:**
- `ssp126` - Best Case Scenario
- `ssp245` - Middle of the Road
- `ssp370` - Upper Middle Scenario *(NEW!)*
- `ssp585` - Worst Case Scenario

**Examples:**
- `2050_ssp245_50.epw` - Year 2050, Middle of the Road, 50th percentile
- `2070_ssp370_99.epw` - Year 2070, Upper Middle Scenario, 99th percentile
- `2090_ssp585_1.epw` - Year 2090, Worst Case Scenario, 1st percentile

## Example Workflows

### Quick Test Run
1. Go to "EPW Morphing" tab
2. Enter project name: `test_run`
3. Upload EPW file
4. Check "Auto-detect from EPW file"
5. Click "Conservative" preset
6. Click "RUN MORPHING"

Result: Single morphed file for 2050, middle pathway, median warming

### Comprehensive Analysis
1. Go to "EPW Morphing" tab
2. Enter project name: `comprehensive_analysis`
3. Upload EPW file
4. Click "Comprehensive" preset
5. Optionally adjust model sources or variables
6. Click "RUN MORPHING"

Result: 36 morphed files covering all scenarios and key percentiles for three future periods

### Custom Configuration
1. Select specific pathways (e.g., Middle + Worst Case)
2. Choose specific years (e.g., `2050,2100`)
3. Select percentiles (e.g., 10th, 50th, 90th)
4. Choose variables (e.g., Temperature, Humidity, Pressure)
5. Adjust model sources if needed
6. Run morphing

Result: Custom set of files matching your exact specifications

### Managing Cache
1. Switch to "Cache Management" tab
2. Click "Refresh" to update statistics
3. Review cached files and sizes
4. If needed, click "Clear Cache" to free up space
5. Cache will rebuild automatically during next morphing operation

## Performance Tips

1. **Use Cache Effectively**: 
   - The cache stores location-specific data
   - Running multiple morphing operations for the same location is much faster
   - First run downloads data; subsequent runs are cached

2. **Start Small**:
   - Test with one pathway and one year first
   - Use "Conservative" preset for quick testing
   - Expand to "Comprehensive" once you verify everything works

3. **Network Considerations**:
   - First-time downloads can be slow depending on network
   - Progress messages in the log show what's happening
   - Consider starting with fewer model sources for faster testing

4. **Cache Management**:
   - Monitor cache size in Cache Management tab
   - Clear cache if testing many different locations
   - Cache automatically manages itself (removes old files when full)

## Troubleshooting

### "Please select at least one..."
Make sure you've selected at least one option from each required section.

### Processing takes a long time
First-time processing downloads climate data. Monitor the log for progress. Subsequent runs for the same location are much faster due to caching.

### Cache fills up quickly
The cache has a 50 MB limit and auto-cleans old files. Clear manually from Cache Management tab if needed.

### GUI becomes unresponsive
Processing runs in background thread, but very heavy log output can slow the GUI. This is normal; wait for completion.

### Can't find output files
Check the "Output Directory" field. By default it's `./morphing_output` relative to where you run the script.

## Development Notes

This GUI is designed for development and testing. Features:
- Full access to all morphing configuration options
- Real-time logging of all operations
- Cache inspection and management
- Quick presets for common scenarios
- Model source selection for testing different data sources

## File Structure

```
gui/
├── __init__.py          # Module initialization
├── main_window.py       # Main window with tabbed interface
├── morph_tab.py         # EPW morphing tab
├── cache_tab.py         # Cache management tab
└── README.md            # This file

run_gui.py               # Launcher script (use this to start GUI)
```

## Requirements

- Python 3.7+
- tkinter (usually included with Python)
- pyepwmorph package with all dependencies
- Internet connection (for downloading climate data)

## Version History

### v2.0 (Current)
- Tabbed interface
- Upper Middle Scenario (SSP3-7.0) support
- Cache management tab
- Model source selection
- Quick presets
- Enhanced tooltips and descriptions
- Improved logging and status indicators

### v1.0 (dev_gui.py)
- Initial single-window GUI
- Basic morphing functionality
- Three SSP scenarios
- Simple cache clearing

