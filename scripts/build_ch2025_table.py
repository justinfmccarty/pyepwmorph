#!/usr/bin/env python3
"""Build the shipped CH2025 monthly climatology tables.

Downloads MeteoSwiss CH2025 DAILY-LOCAL station CSVs and reduces each
model chain to a 12-month climatology over the 30 synthetic climate years.
The result is written into the package data directory:

    pyepwmorph/data/ch2025_monthly.parquet
    pyepwmorph/data/ch2025_stations.parquet

Re-run this when MeteoSwiss publishes a new CH2025 release. A partial
parquet is kept beside the outputs so an interrupted run can resume.

CH2025 data is CC-BY. Cite:
MeteoSwiss & ETH Zurich (2025): Climate CH2025 - Daily Datasets.
https://doi.org/10.18751/climate/scenarios/ch2025/data/1.0/
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger("build_ch2025_table")

STAC_ROOT = "https://data.geo.admin.ch/api/stac/v1"
COLLECTION = "ch.meteoschweiz.ogd-climate-scenarios-ch2025"
ASSET_ROOT = (
    "https://rgw.cscs.ch/mchogd:cscs.meteoswiss.ogd.climate/"
    "ogd-climate-scenarios-ch2025"
)

STATES = ("ref91-20", "gwl1.5", "gwl2.0", "gwl2.5", "gwl3.0")
REQUIRED = frozenset({"tas", "tasmax", "tasmin"})
WANTED = frozenset({"tas", "tasmax", "tasmin", "hurs", "rsds", "sfcwind"})
CANONICAL = {"sfcwind": "sfcWind"}

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "pyepwmorph" / "data"
MONTHLY_PATH = DATA_DIR / "ch2025_monthly.parquet"
STATIONS_PATH = DATA_DIR / "ch2025_stations.parquet"
PARTIAL_PATH = DATA_DIR / ".ch2025_build_partial.parquet"


def _fetch(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "pyepwmorph-ch2025-build"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _fetch_json(url: str) -> dict:
    return json.loads(_fetch(url).decode("utf-8"))


def canonical_variable(token: str) -> str:
    return CANONICAL.get(token, token)


def filename_token(variable: str) -> str:
    return "sfcwind" if variable == "sfcWind" else variable


def discover_stations() -> dict[str, set[str]]:
    """Map station id -> filename variable tokens present as CSV assets."""
    url = f"{STAC_ROOT}/collections/{COLLECTION}/items?limit=100"
    capabilities: dict[str, set[str]] = {}
    while url:
        payload = _fetch_json(url)
        for feature in payload.get("features", []):
            tokens = set()
            for key in feature.get("assets", {}):
                if not key.endswith(".csv"):
                    continue
                parts = key[: -len(".csv")].split("_")
                if len(parts) >= 4:
                    tokens.add(parts[-2])
            capabilities[feature["id"].lower()] = tokens
        url = None
        for link in payload.get("links", []):
            if link.get("rel") == "next":
                url = link.get("href")
    return capabilities


def load_station_metadata() -> pd.DataFrame:
    collection = _fetch_json(f"{STAC_ROOT}/collections/{COLLECTION}")
    href = collection["assets"]["ogd-climate-scenarios-ch2025_meta_stations.csv"]["href"]
    raw = _fetch(href).decode("utf-8-sig")
    frame = pd.read_csv(io.StringIO(raw), sep=";")
    frame.columns = [column.strip().lower() for column in frame.columns]

    def pick(*needles: str) -> str:
        for column in frame.columns:
            if all(needle in column for needle in needles):
                return column
        raise KeyError(f"No metadata column matching {needles} in {list(frame.columns)}")

    abbr = pick("abbr")
    name = pick("station_name")
    height = pick("height_masl")
    lat = next(column for column in frame.columns if "lat" in column)
    lon = next(column for column in frame.columns if "lon" in column or "lng" in column)
    out = pd.DataFrame(
        {
            "station_id": frame[abbr].astype(str).str.lower(),
            "name": frame[name].astype(str),
            "latitude": pd.to_numeric(frame[lat], errors="coerce"),
            "longitude": pd.to_numeric(frame[lon], errors="coerce"),
            "elevation": pd.to_numeric(frame[height], errors="coerce"),
        }
    )
    return out.drop_duplicates("station_id").set_index("station_id")


def asset_url(station_id: str, variable: str, state: str) -> str:
    token = filename_token(variable)
    name = f"ogd-climate-scenarios-ch2025_{station_id}_{token}_{state}.csv"
    return f"{ASSET_ROOT}/{station_id}/{name}"


def monthly_climatology(raw: bytes) -> tuple[pd.DataFrame, dict[str, str]]:
    text = raw.decode("utf-8-sig")
    lines = text.splitlines()
    blank = next(index for index, line in enumerate(lines) if line.strip() == "")
    metadata = {}
    for line in lines[:blank]:
        key, _, value = line.partition(";")
        metadata[key.strip()] = value.strip()
    frame = pd.read_csv(
        io.StringIO("\n".join(lines[blank + 1 :])),
        sep=";",
        na_values=["NA"],
    )
    frame["month"] = frame["DATE"].astype(str).str.slice(5, 7).astype(int)
    chains = [column for column in frame.columns if column not in ("DATE", "month")]
    climatology = frame.groupby("month", sort=True)[chains].mean()
    return climatology, metadata


def reduce_asset(station_id: str, variable: str, state: str) -> tuple[pd.DataFrame, dict[str, str]]:
    climatology, metadata = monthly_climatology(_fetch(asset_url(station_id, variable, state)))
    long = climatology.reset_index().melt(id_vars="month", var_name="chain", value_name="value")
    long.insert(0, "station_id", station_id)
    long.insert(1, "variable", variable)
    long.insert(2, "state", state)
    long["value"] = long["value"].astype("float32")
    long["month"] = long["month"].astype("int8")
    return long, metadata


def load_partial() -> pd.DataFrame:
    if not PARTIAL_PATH.exists():
        return pd.DataFrame(columns=["station_id", "variable", "state", "chain", "month", "value"])
    return pd.read_parquet(PARTIAL_PATH)


def write_partial(frame: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(PARTIAL_PATH, index=False)


def write_with_metadata(frame: pd.DataFrame, path: Path, metadata: dict[str, str]) -> None:
    table = pa.Table.from_pandas(frame, preserve_index=False)
    existing = table.schema.metadata or {}
    existing.update({key.encode(): value.encode() for key, value in metadata.items()})
    table = table.replace_schema_metadata(existing)
    pq.write_table(table, path, compression="zstd")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit-stations", type=int, default=0, help="0 means all capable stations")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()

    logger.info("Discovering station capabilities")
    capabilities = discover_stations()
    logger.info("Loading station metadata")
    metadata = load_station_metadata()

    jobs = []
    station_rows = []
    for station_id, tokens in sorted(capabilities.items()):
        if not REQUIRED <= tokens:
            continue
        variables = sorted(canonical_variable(token) for token in tokens if token in WANTED)
        if station_id not in metadata.index:
            logger.warning("No metadata for station %s; skipping", station_id)
            continue
        row = metadata.loc[station_id]
        station_rows.append(
            {
                "station_id": station_id,
                "name": row["name"],
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "elevation": float(row["elevation"]),
                "variables": variables,
            }
        )
        for variable in variables:
            for state in STATES:
                jobs.append((station_id, variable, state))

    if args.limit_stations:
        keep = {row["station_id"] for row in station_rows[: args.limit_stations]}
        station_rows = [row for row in station_rows if row["station_id"] in keep]
        jobs = [job for job in jobs if job[0] in keep]

    stations = pd.DataFrame(station_rows)
    logger.info("%d stations, %d assets", len(stations), len(jobs))

    partial = load_partial()
    done = set()
    if not partial.empty:
        done = set(zip(partial["station_id"], partial["variable"], partial["state"]))
        logger.info("Resuming: %d assets already reduced", len(done))
    pending = [job for job in jobs if job not in done]

    pieces = [partial] if not partial.empty else []
    provenance: dict[str, str] = {}
    completed_since_flush = 0

    def _flush() -> None:
        if not pieces:
            return
        combined = pd.concat(pieces, ignore_index=True)
        write_partial(combined)
        pieces.clear()
        pieces.append(combined)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(reduce_asset, *job): job for job in pending}
        for index, future in enumerate(as_completed(futures), start=1):
            job = futures[future]
            try:
                frame, file_meta = future.result()
            except Exception as exc:
                logger.error("Failed %s: %s", job, exc)
                _flush()
                raise
            pieces.append(frame)
            provenance.setdefault("ch2025_version", file_meta.get("VERSION", ""))
            provenance.setdefault("ch2025_creation_date", file_meta.get("CREATION_DATE", ""))
            provenance.setdefault("citation", file_meta.get("CITATION", ""))
            completed_since_flush += 1
            if index % 25 == 0 or index == len(pending):
                logger.info("Reduced %d / %d", index, len(pending))
            if completed_since_flush >= 50:
                _flush()
                completed_since_flush = 0

    monthly = pd.concat(pieces, ignore_index=True) if pieces else partial
    monthly = monthly.sort_values(
        ["station_id", "variable", "state", "chain", "month"], kind="stable",
    ).reset_index(drop=True)

    provenance.setdefault("source", "MeteoSwiss CH2025 DAILY-LOCAL")
    provenance.setdefault("license", "CC-BY-4.0")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_with_metadata(monthly, MONTHLY_PATH, provenance)

    stations_table = pa.Table.from_pandas(stations, preserve_index=False)
    existing = stations_table.schema.metadata or {}
    existing.update({key.encode(): value.encode() for key, value in provenance.items()})
    pq.write_table(stations_table.replace_schema_metadata(existing), STATIONS_PATH, compression="zstd")

    if PARTIAL_PATH.exists():
        PARTIAL_PATH.unlink()

    logger.info("Wrote %s (%d rows) and %s (%d stations)", MONTHLY_PATH, len(monthly), STATIONS_PATH, len(stations))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
