"""
Caching utilities for pyepwmorph to store and retrieve location-specific processed CMIP6 data.

Data is cached after it has been spatially selected and computed for specific
coordinates, so a cache key identifies a location, a pathway, a variable, a set
of model sources, and the temporal slices those sources were cut to.
"""

import hashlib
import json
import logging
import os
import pickle
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023-2026"
__credits__ = ["Justin McCarty"]
__license__ = "MIT"

__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"

#: Bumped whenever the shape of the cached payload changes, so that stale
#: entries written by an older release are never read back.
CACHE_SCHEMA_VERSION = 2

#: Environment variable overrides, useful on shared machines and in CI.
CACHE_DIR_ENV_VAR = "PYEPWMORPH_CACHE_DIR"
CACHE_MAX_SIZE_ENV_VAR = "PYEPWMORPH_CACHE_MAX_MB"

DEFAULT_CACHE_MAX_SIZE_MB = 500.0


def _default_cache_dir() -> Path:
    """Return the per-user cache directory for this platform."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base) / "pyepwmorph"


def get_cache_dir() -> Path:
    """Return the directory cached data is written to.

    Set the ``PYEPWMORPH_CACHE_DIR`` environment variable to override it.
    """
    override = os.environ.get(CACHE_DIR_ENV_VAR)
    return Path(override) if override else _default_cache_dir()


def get_cache_max_size_mb() -> float:
    """Return the cache size cap in MB.

    Set the ``PYEPWMORPH_CACHE_MAX_MB`` environment variable to override it.
    """
    override = os.environ.get(CACHE_MAX_SIZE_ENV_VAR)
    if not override:
        return DEFAULT_CACHE_MAX_SIZE_MB
    try:
        return float(override)
    except ValueError:
        logger.warning(
            "Ignoring invalid %s=%r, falling back to %s MB",
            CACHE_MAX_SIZE_ENV_VAR, override, DEFAULT_CACHE_MAX_SIZE_MB,
        )
        return DEFAULT_CACHE_MAX_SIZE_MB


def _ensure_cache_dir() -> Path:
    """Ensure the cache directory exists and return it."""
    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_coordinate_cache_key(latitude: float, longitude: float, pathway: str,
                              variable: str, source_id: List[str],
                              time_slices: Optional[Dict] = None) -> str:
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
    time_slices : dict or None
        Temporal bounds the data was cut to.  Different bounds must not share
        a cache entry.

    Returns
    -------
    str
        Structured cache key for processed climate model data
    """
    sources_str = "_".join(sorted(source_id)).lower().replace("-", "")

    # Round coordinates to a fixed precision so that floating point noise does
    # not produce spurious cache misses.
    lat_str = f"{latitude:.4f}".replace(".", "p").replace("-", "n")
    lon_str = f"{longitude:.4f}".replace(".", "p").replace("-", "n")

    slices_digest = hashlib.sha1(
        json.dumps(time_slices or {}, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:8]

    key_parts = [
        f"v{CACHE_SCHEMA_VERSION}",
        "coordinate",
        f"lat_{lat_str}",
        f"lon_{lon_str}",
        f"pathway_{pathway}",
        f"variable_{variable}",
        f"sources_{sources_str}",
        f"slices_{slices_digest}",
    ]

    return "__".join(key_parts)


def _get_cache_filepath(cache_key: str) -> Path:
    """Get the full filepath for a cache key."""
    return get_cache_dir() / f"{cache_key}.pkl"


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
    cache_dir = _ensure_cache_dir()
    cache_files = []

    for filepath in cache_dir.glob("*.pkl"):
        cache_files.append((filepath, _get_file_size_mb(filepath), filepath.stat().st_mtime))

    return cache_files


def _cleanup_cache_if_needed():
    """Remove oldest cache files if total size exceeds limit."""
    max_size_mb = get_cache_max_size_mb()
    cache_files = _get_cache_files_with_stats()
    total_size_mb = sum(size for _, size, _ in cache_files)

    if total_size_mb <= max_size_mb:
        return

    # Sort by modification time (oldest first)
    cache_files.sort(key=lambda entry: entry[2])

    for filepath, size_mb, _ in cache_files:
        if total_size_mb <= max_size_mb:
            break
        filepath.unlink(missing_ok=True)
        total_size_mb -= size_mb
        logger.info("Cache cleanup: removed %s (%.2f MB)", filepath.name, size_mb)


def get_cached_coordinate_data(latitude: float, longitude: float, pathway: str,
                               variable: str, source_id: List[str],
                               time_slices: Optional[Dict] = None) -> Optional[Dict]:
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
    time_slices : dict or None
        Temporal bounds the data was cut to

    Returns
    -------
    Optional[Dict]
        Cached coordinate dataset dictionary or None if not found
    """
    _ensure_cache_dir()

    cache_key = _get_coordinate_cache_key(latitude, longitude, pathway, variable, source_id, time_slices)
    cache_filepath = _get_cache_filepath(cache_key)

    if not cache_filepath.exists():
        return None

    try:
        with open(cache_filepath, 'rb') as fh:
            cached_data = pickle.load(fh)
    except (OSError, pickle.PickleError, EOFError, AttributeError) as exc:
        logger.warning("Cache read failed for %s (%s); discarding entry", cache_key, exc)
        cache_filepath.unlink(missing_ok=True)
        return None

    logger.info("Cache hit for %s", cache_key)
    return cached_data


def save_coordinate_to_cache(data: Dict, latitude: float, longitude: float, pathway: str,
                             variable: str, source_id: List[str],
                             time_slices: Optional[Dict] = None):
    """
    Save coordinate data to cache.

    Parameters
    ----------
    data : Dict
        Coordinate dataset dictionary to cache
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
    time_slices : dict or None
        Temporal bounds the data was cut to
    """
    _ensure_cache_dir()

    cache_key = _get_coordinate_cache_key(latitude, longitude, pathway, variable, source_id, time_slices)
    cache_filepath = _get_cache_filepath(cache_key)

    try:
        with open(cache_filepath, 'wb') as fh:
            pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except (OSError, pickle.PickleError) as exc:
        logger.warning("Cache write failed for %s (%s)", cache_key, exc)
        cache_filepath.unlink(missing_ok=True)
        return

    logger.info("Cached %s (%.2f MB)", cache_key, _get_file_size_mb(cache_filepath))
    _cleanup_cache_if_needed()


def clear_cache():
    """Clear all cached data."""
    cache_dir = _ensure_cache_dir()

    removed_count = 0
    total_size_mb = 0.0

    for filepath in cache_dir.glob("*.pkl"):
        total_size_mb += _get_file_size_mb(filepath)
        filepath.unlink(missing_ok=True)
        removed_count += 1

    logger.info("Cache cleared: removed %d files (%.2f MB)", removed_count, total_size_mb)
    return {"removed_files": removed_count, "freed_mb": round(total_size_mb, 2)}


def get_cache_stats() -> Dict[str, Any]:
    """
    Get cache statistics.

    Returns
    -------
    Dict[str, Any]
        Dictionary containing cache statistics
    """
    cache_dir = _ensure_cache_dir()
    max_size_mb = get_cache_max_size_mb()
    cache_files = _get_cache_files_with_stats()

    total_size_mb = sum(size for _, size, _ in cache_files)

    # Sort by modification time (newest first) for display
    cache_files.sort(key=lambda entry: entry[2], reverse=True)

    file_info = [
        {
            "filename": filepath.name,
            "size_mb": round(size_mb, 2),
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
        }
        for filepath, size_mb, mtime in cache_files
    ]

    return {
        "cache_directory": str(cache_dir),
        "total_files": len(cache_files),
        "total_size_mb": round(total_size_mb, 2),
        "max_size_mb": max_size_mb,
        "usage_percent": round((total_size_mb / max_size_mb) * 100, 1) if max_size_mb else 0.0,
        "files": file_info,
    }
