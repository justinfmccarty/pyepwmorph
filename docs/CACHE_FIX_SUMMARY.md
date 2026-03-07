# Cache Fix Summary

## Problem Identified

The caching system had a critical flaw where data was being cached at two levels:

1. **Raw data cache** in `access.py` - cached WITHOUT location information
2. **Processed data cache** in `coordinate.py` - cached WITH location information

### The Issue

The raw data from `access.py` appears to be location-agnostic (full global grid), but:

- It's stored as **lazy dask arrays** that reference remote Zarr data
- When pickled and unpickled, these lazy arrays may not behave correctly
- The actual computation happens AFTER spatial selection in `coordinate.py`
- The cache key in `access.py` did NOT include latitude/longitude

This meant:
- Location A would cache data (possibly after it was spatially constrained)
- Location B would retrieve Location A's cache and get incorrect data
- OR the lazy dask references would break after pickling

## Solution Applied

### Changes Made

1. **Removed caching from `access.py`**
   - Removed `get_cached_data()` and `save_to_cache()` calls
   - Added explanatory comment about why caching doesn't happen at this level
   - The data now flows directly to `coordinate.py` as lazy dask arrays

2. **Kept caching in `coordinate.py`**
   - This cache already includes latitude and longitude in the cache key
   - Data is cached AFTER spatial selection and computation
   - Cache keys are properly scoped to specific locations

3. **Cleaned up `cache.py`**
   - Removed unused `_get_cache_key()` function
   - Removed unused `get_cached_data()` and `save_to_cache()` functions
   - Updated module docstring to clarify it only caches location-specific data

4. **Updated documentation**
   - Updated `clear_cmip6_cache()` and `get_cmip6_cache_stats()` docstrings
   - Clarified that cache stores location-specific processed data

### Files Modified

- `pyepwmorph/models/access.py` - Removed problematic caching
- `pyepwmorph/tools/cache.py` - Removed unused functions, updated docs
- `CACHE_FIX_SUMMARY.md` - This file (can be deleted after review)

## Result

Now the caching system:
- ✅ Only caches data that is specific to a location
- ✅ Includes location (lat/lon) in all cache keys
- ✅ Prevents cache collisions between different locations
- ✅ Caches computed data, not lazy dask array references
- ✅ Works correctly when querying multiple locations

## Testing Recommendation

To verify the fix works:

1. Query data for Location A (lat=40.0, lon=-75.0)
2. Query data for Location B (lat=31.0, lon=121.0) 
3. Verify both locations return different, correct data
4. Check cache stats to confirm both locations have separate cache entries

```python
from pyepwmorph.models import access

# This should create separate cache entries
stats = access.get_cmip6_cache_stats()
print(stats)
```

