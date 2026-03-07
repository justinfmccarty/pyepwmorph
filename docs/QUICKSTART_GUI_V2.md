# Quick Start Guide - PyEPWMorph GUI v2.0

## Launch the GUI

```bash
python run_gui.py
```

That's it! The new tabbed interface will open.

## 30-Second Test Run

1. **EPW Morphing** tab (should be open by default)
2. Project name: `test`
3. Click **"Choose File"** → select your EPW
4. Click **"Conservative"** preset button
5. Click **"RUN MORPHING"**
6. Watch the log for progress
7. Done! Check `./morphing_output/` folder

**Result**: One morphed EPW file for 2050, middle pathway, median warming.

## What's New in v2.0?

### ✨ Upper Middle Scenario
- **NEW SSP3-7.0 pathway** now available
- Total of 4 climate pathways (was 3)

### 📊 Cache Management Tab
- **View cache statistics** in real-time
- **See cached files** with details
- **Clear cache** when needed
- **Open cache location** in file explorer

### 🎛️ Model Source Selection
- Choose which models to use:
  - ACCESS-CM2 (Australian)
  - CanESM5 (Canadian)
  - TaiESM1 (Taiwanese)

### ⚡ Quick Presets
- **Conservative**: Fast test (1 file)
- **Comprehensive**: Full analysis (36 files)

### 📝 Better Descriptions
- Each variable shows required climate data
- Each pathway shows scenario description
- Enhanced logging with ✓ and ✗ symbols

## Tab Overview

### Tab 1: EPW Morphing
Everything you need to morph EPW files:
- Project configuration
- Baseline period (with auto-detect)
- Model sources
- Climate pathways (4 options)
- Future years
- Percentiles (9 options)
- Variables to morph (6 options)
- Quick preset buttons
- Real-time processing log

### Tab 2: Cache Management
Monitor and manage your cache:
- Cache statistics (size, files, usage)
- File listing with details
- Clear cache button
- Open cache location
- Educational info about caching

## Quick Examples

### Example 1: Conservative Test
```
Project name: test
EPW: (your file)
Click: "Conservative" preset
Click: "RUN MORPHING"
→ Generates: 1 file (2050_ssp245_50.epw)
```

### Example 2: Comprehensive Analysis
```
Project name: full_analysis
EPW: (your file)
Click: "Comprehensive" preset
Click: "RUN MORPHING"
→ Generates: 36 files covering all scenarios
```

### Example 3: Custom Selection
```
Project name: custom
EPW: (your file)
Pathways: ☑ Middle ☑ Upper Middle
Years: 2050,2070
Percentiles: ☑ 10th ☑ 50th ☑ 90th
Variables: ☑ Temperature ☑ Humidity
Click: "RUN MORPHING"
→ Generates: 12 files (2 pathways × 2 years × 3 percentiles)
```

## Cache Management

After running some morphs:

1. Switch to **"Cache Management"** tab
2. Click **"Refresh"** to update stats
3. See cache size and file count
4. Review cached files in the tree view
5. Click **"View Cache Location"** to open folder
6. Click **"Clear Cache"** if needed (with confirmation)

## File Output

Files are named: `{year}_{pathway}_{percentile}.epw`

**Pathway codes:**
- `ssp126` = Best Case Scenario
- `ssp245` = Middle of the Road
- `ssp370` = Upper Middle Scenario ← **NEW!**
- `ssp585` = Worst Case Scenario

**Examples:**
- `2050_ssp245_50.epw`
- `2070_ssp370_99.epw` ← **NEW pathway!**
- `2090_ssp585_1.epw`

## Presets Explained

### Conservative Preset
Perfect for testing:
- **1 pathway**: Middle of the Road (ssp245)
- **1 percentile**: 50th (median)
- **1 variable**: Temperature
- **1 year**: 2050
- **Result**: 1 file in ~2-5 minutes

### Comprehensive Preset
Full analysis:
- **4 pathways**: All scenarios
- **3 percentiles**: 1st, 50th, 99th (low, median, high)
- **6 variables**: All available
- **3 years**: 2050, 2070, 2090
- **Result**: 36 files in ~10-30 minutes

## Tips

### First Time
- Start with "Conservative" preset
- Verify everything works
- Check output file
- Then expand to more scenarios

### Cache
- First run downloads data (slower)
- Subsequent runs use cache (faster)
- Same location = reuse cache
- Different location = new downloads

### Performance
- More selections = longer processing
- Network speed affects first run
- Cache makes repeated runs fast
- Log shows progress throughout

## Troubleshooting

### GUI won't start
```bash
# Make sure you're in the right directory
cd /path/to/pyepwmorph
python run_gui.py
```

### "No module named gui"
```bash
# Verify the gui folder exists
ls -l gui/
# Should show: __init__.py, main_window.py, morph_tab.py, cache_tab.py
```

### Processing takes forever
- Check log for progress
- First run downloads data (be patient)
- Subsequent runs are faster (cached)
- Try "Conservative" preset first

### Can't find output files
- Check "Output Directory" field
- Default: `./morphing_output`
- Relative to where you run the script
- Look for success message in log

### Want to use old GUI
```bash
python dev_gui.py
```
Both GUIs work - use whichever you prefer!

## Need More Help?

- **Full Documentation**: See `gui/README.md`
- **Comparison**: See `GUI_COMPARISON.md`
- **Implementation Details**: See `GUI_V2_SUMMARY.md`
- **Original GUI**: See `DEV_GUI_README.md`

## What's Working Right Now

The GUI should be running! If you just ran the command, you should see:
- A window titled "PyEPWMorph - Development GUI v2.0"
- Two tabs: "EPW Morphing" and "Cache Management"
- All controls ready to use

Try the 30-second test run above to verify everything works!

## Version Note

- **This is v2.0** - Enhanced GUI with tabs
- **Original v1.0** - Still available as `dev_gui.py`
- **Both work** - Choose based on needs
- **Same output** - Compatible file formats
- **Same workflow** - Uses same underlying code

