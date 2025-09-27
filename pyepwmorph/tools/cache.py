# coding=utf-8
"""
Caching utilities for pyepwmorph to store and retrieve CMIP6 data
"""

import pickle
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import time

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023"
__credits__ = ["Justin McCarty"]
__license__ = "GPLv3"
__version__ = "0.1"
__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"

# Cache configuration
CACHE_MAX_SIZE_MB = 50
CACHE_DIR = Path(tempfile.gettempdir()) / "pyepwmorph_cache"


def _ensure_cache_dir():
    """Ensure the cache directory exists."""
    CACHE_DIR.mkdir(exist_ok=True)


def _get_cache_key(experiment_id: str, table_id: str, variable_id: str, 
                   member_id: str, source_id: List[str]) -> str:
    """
    Generate a structured cache key from search parameters.
    
    Parameters
    ----------
    experiment_id : str
        The experiment ID (pathway)
    table_id : str
        The table ID (e.g., 'Amon')
    variable_id : str
        The variable ID
    member_id : str
        The member ID (e.g., 'r1i1p1f1')
    source_id : List[str]
        List of model sources
        
    Returns
    -------
    str
        Structured cache key
    """
    # Sort source_id list to handle different ordering
    sorted_sources = sorted(source_id)
    sources_str = "_".join(sorted_sources).lower().replace("-", "")
    
    key_parts = [
        f"experiment_{experiment_id}",
        f"table_{table_id}",
        f"variable_{variable_id}",
        f"member_{member_id}",
        f"sources_{sources_str}"
    ]
    
    return "__".join(key_parts)


def _get_coordinate_cache_key(latitude: float, longitude: float, pathway: str, 
                             variable: str, source_id: List[str]) -> str:
    """
    Generate a structured cache key for data that has been processed by the scripts in coordinate.py.
    
    Parameters
    ----------
    latitude : float
        The latitude coordinate
    longitude : float
        The longitude coordinate
    pathway : str
        The pathway/experiment ID
    variable : str
        The variable ID
    source_id : List[str]
        List of model sources
        
    Returns
    -------
    str
        Structured cache key for processed climate model data
    """
    # Sort source_id list to handle different ordering
    sorted_sources = sorted(source_id)
    sources_str = "_".join(sorted_sources).lower().replace("-", "")
    
    # Round coordinates to reasonable precision to avoid cache misses due to floating point precision
    lat_str = f"{latitude:.4f}".replace(".", "p").replace("-", "n")
    lon_str = f"{longitude:.4f}".replace(".", "p").replace("-", "n")
    
    key_parts = [
        "coordinate",  # Prefix to distinguish from access cache
        f"lat_{lat_str}",
        f"lon_{lon_str}",
        f"pathway_{pathway}",
        f"variable_{variable}",
        f"sources_{sources_str}"
    ]
    
    return "__".join(key_parts)


def _get_cache_filepath(cache_key: str) -> Path:
    """Get the full filepath for a cache key."""
    return CACHE_DIR / f"{cache_key}.pkl"


def _get_file_size_mb(filepath: Path) -> float:
    """Get file size in MB."""
    if not filepath.exists():
        return 0.0
    return filepath.stat().st_size / (1024 * 1024)


def _get_cache_files_with_stats() -> List[Tuple[Path, float, float]]:
    """
    Get all cache files with their sizes and modification times.
    
    Returns
    -------
    List[Tuple[Path, float, float]]
        List of (filepath, size_mb, mtime) tuples
    """
    _ensure_cache_dir()
    cache_files = []
    
    for filepath in CACHE_DIR.glob("*.pkl"):
        size_mb = _get_file_size_mb(filepath)
        mtime = filepath.stat().st_mtime
        cache_files.append((filepath, size_mb, mtime))
    
    return cache_files


def _cleanup_cache_if_needed():
    """Remove oldest cache files if total size exceeds limit."""
    cache_files = _get_cache_files_with_stats()
    total_size_mb = sum(size for _, size, _ in cache_files)
    
    if total_size_mb <= CACHE_MAX_SIZE_MB:
        return
    
    # Sort by modification time (oldest first)
    cache_files.sort(key=lambda x: x[2])
    
    # Remove oldest files until we're under the limit
    for filepath, size_mb, _ in cache_files:
        if total_size_mb <= CACHE_MAX_SIZE_MB:
            break
        
        filepath.unlink()
        total_size_mb -= size_mb
        print(f"Cache cleanup: Removed {filepath.name} ({size_mb:.2f} MB)")


def get_cached_data(experiment_id: str, table_id: str, variable_id: str, 
                   member_id: str, source_id: List[str]) -> Optional[Dict]:
    """
    Retrieve cached CMIP6 data if it exists.
    
    Parameters
    ----------
    experiment_id : str
        The experiment ID (pathway)
    table_id : str
        The table ID (e.g., 'Amon')
    variable_id : str
        The variable ID
    member_id : str
        The member ID (e.g., 'r1i1p1f1')
    source_id : List[str]
        List of model sources
        
    Returns
    -------
    Optional[Dict]
        Cached dataset dictionary or None if not found
    """
    _ensure_cache_dir()
    
    cache_key = _get_cache_key(experiment_id, table_id, variable_id, member_id, source_id)
    cache_filepath = _get_cache_filepath(cache_key)
    
    if not cache_filepath.exists():
        return None
    
    try:
        with open(cache_filepath, 'rb') as f:
            cached_data = pickle.load(f)
        print(f"Cache hit: Loaded data for {cache_key}")
        return cached_data
    except (IOError, pickle.PickleError) as e:
        print(f"Cache read error for {cache_key}: {e}")
        # Remove corrupted cache file
        cache_filepath.unlink()
        return None


def save_to_cache(data: Dict, experiment_id: str, table_id: str, variable_id: str, 
                 member_id: str, source_id: List[str]):
    """
    Save CMIP6 data to cache.
    
    Parameters
    ----------
    data : Dict
        Dataset dictionary to cache
    experiment_id : str
        The experiment ID (pathway)
    table_id : str
        The table ID (e.g., 'Amon')
    variable_id : str
        The variable ID
    member_id : str
        The member ID (e.g., 'r1i1p1f1')
    source_id : List[str]
        List of model sources
    """
    _ensure_cache_dir()
    
    cache_key = _get_cache_key(experiment_id, table_id, variable_id, member_id, source_id)
    cache_filepath = _get_cache_filepath(cache_key)
    
    try:
        with open(cache_filepath, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        size_mb = _get_file_size_mb(cache_filepath)
        print(f"Cache save: Stored data for {cache_key} ({size_mb:.2f} MB)")
        
        # Clean up cache if needed
        _cleanup_cache_if_needed()
        
    except (IOError, pickle.PickleError) as e:
        print(f"Cache write error for {cache_key}: {e}")


def get_cached_coordinate_data(latitude: float, longitude: float, pathway: str, 
                              variable: str, source_id: List[str]) -> Optional[Dict]:
    """
    Retrieve cached coordinate data if it exists.
    
    Parameters
    ----------
    latitude : float
        The latitude coordinate
    longitude : float
        The longitude coordinate
    pathway : str
        The pathway/experiment ID
    variable : str
        The variable ID
    source_id : List[str]
        List of model sources
        
    Returns
    -------
    Optional[Dict]
        Cached coordinate dataset dictionary or None if not found
    """
    _ensure_cache_dir()
    
    cache_key = _get_coordinate_cache_key(latitude, longitude, pathway, variable, source_id)
    cache_filepath = _get_cache_filepath(cache_key)
    
    if not cache_filepath.exists():
        return None
    
    try:
        with open(cache_filepath, 'rb') as f:
            cached_data = pickle.load(f)
        print(f"Cache hit: Loaded data processed by coordinate script for {cache_key}")
        return cached_data
    except (IOError, pickle.PickleError) as e:
        print(f"Cache read error for coordinate data {cache_key}: {e}")
        # Remove corrupted cache file
        cache_filepath.unlink()
        return None


def save_coordinate_to_cache(data: Dict, latitude: float, longitude: float, pathway: str, 
                            variable: str, source_id: List[str]):
    """
    Save coordinate data to cache.
    
    Parameters
    ----------
    data : Dict
        Coordinate.py dataset dictionary to cache
    latitude : float
        The latitude coordinate
    longitude : float
        The longitude coordinate
    pathway : str
        The pathway/experiment ID
    variable : str
        The variable ID
    source_id : List[str]
        List of model sources
    """
    _ensure_cache_dir()
    
    cache_key = _get_coordinate_cache_key(latitude, longitude, pathway, variable, source_id)
    cache_filepath = _get_cache_filepath(cache_key)
    
    try:
        with open(cache_filepath, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        size_mb = _get_file_size_mb(cache_filepath)
        print(f"Cache save: Stored coordinate data for {cache_key} ({size_mb:.2f} MB)")
        
        # Clean up cache if needed
        _cleanup_cache_if_needed()
        
    except (IOError, pickle.PickleError) as e:
        print(f"Cache write error for coordinate data {cache_key}: {e}")


def clear_cache():
    """Clear all cached data."""
    _ensure_cache_dir()
    
    removed_count = 0
    total_size_mb = 0.0
    
    for filepath in CACHE_DIR.glob("*.pkl"):
        size_mb = _get_file_size_mb(filepath)
        filepath.unlink()
        removed_count += 1
        total_size_mb += size_mb
    
    print(f"Cache cleared: Removed {removed_count} files ({total_size_mb:.2f} MB)")


def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics for development use.
    
    Returns
    -------
    Dict[str, Any]
        Dictionary containing cache statistics
    """
    _ensure_cache_dir()
    
    cache_files = _get_cache_files_with_stats()
    
    if not cache_files:
        return {
            "cache_directory": str(CACHE_DIR),
            "total_files": 0,
            "total_size_mb": 0.0,
            "max_size_mb": CACHE_MAX_SIZE_MB,
            "files": []
        }
    
    total_size_mb = sum(size for _, size, _ in cache_files)
    
    # Sort by modification time (newest first) for display
    cache_files.sort(key=lambda x: x[2], reverse=True)
    
    file_info = []
    for filepath, size_mb, mtime in cache_files:
        file_info.append({
            "filename": filepath.name,
            "size_mb": round(size_mb, 2),
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        })
    
    return {
        "cache_directory": str(CACHE_DIR),
        "total_files": len(cache_files),
        "total_size_mb": round(total_size_mb, 2),
        "max_size_mb": CACHE_MAX_SIZE_MB,
        "usage_percent": round((total_size_mb / CACHE_MAX_SIZE_MB) * 100, 1),
        "files": file_info
    }