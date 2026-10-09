#!/usr/bin/env python3
"""Fit the shipped diffuse-fraction tables used by ``pyepwmorph.tools.amy``.

Deprecated with ``pyepwmorph.tools.amy`` (3.4.0): the maintained copy is
``scripts/build_amy_diffuse_table.py`` in weather-file-builder. Removed in 4.0.

Fluntern-type stations measure global irradiance and sunshine duration but
not diffuse irradiance. Stations that do measure diffuse (MeteoSwiss
Zuerich/Affoltern REH and Zuerich/Kloten KLO, 10-minute data) are used to
learn how the hourly diffuse fraction depends on

* the clearness index ``kt`` of the hour,
* the sunshine fraction ``S`` of the hour,
* the standard deviation of ``kt`` across the six 10-minute sub-intervals (``sd``),
* the solar zenith angle.

A gradient-boosted model is fitted and then written out as a regular grid
(``pyepwmorph/data/amy_diffuse_table.parquet``) that the package interpolates,
so the package itself needs no machine-learning dependency. The features come
from ``pyepwmorph.tools.amy`` so fitting and use cannot drift apart.

Needs scikit-learn (not a package dependency): ``pip install scikit-learn``.

Usage::

    python scripts/build_amy_diffuse_table.py \\
        --stations-csv ogd-smn_meta_stations.csv \\
        --station REH=ogd-smn_reh_t_historical_2020-2029.csv \\
        --station KLO=ogd-smn_klo_t_historical_2020-2029.csv

Add ``--holdout 2025`` to fit on the first station before 2025 and report the
error on every station in 2025 instead of writing the table.

Data: MeteoSwiss open government data. The table is a derived product; cite
MeteoSwiss when you publish results that use it.
"""

from __future__ import annotations

import argparse
import itertools
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from pyepwmorph.tools import amy
from pyepwmorph.tools.amy_meteoswiss import meteoswiss_location, read_meteoswiss_ogd

logger = logging.getLogger("build_amy_diffuse_table")

OUTPUT = Path(__file__).resolve().parent.parent / "pyepwmorph" / "data" / "amy_diffuse_table.parquet"

AXES = {
    "kt": np.round(np.arange(0.0, 1.2001, 0.05), 2),
    "S": np.round(np.linspace(0.0, 1.0, 11), 2),
    "sd": np.array([0.0, 0.03, 0.07, 0.12, 0.2, 0.35, 0.5]),
    "zen": np.array([10.0, 30.0, 50.0, 65.0, 75.0, 85.0]),
}


def station_features(csv_path: str, stations_csv: str, station: str) -> pd.DataFrame:
    """Hourly features and the measured diffuse fraction for one station."""
    location = meteoswiss_location(stations_csv, station)
    table = read_meteoswiss_ogd(csv_path)
    hourly, step = amy.aggregate_to_hourly(table, location)
    if step != 10:
        raise SystemExit("the tables are fitted on 10-minute data")
    solar = amy._solar_frame(hourly.index, location)
    ghi = hourly["ghi_Wm2"].clip(lower=0)
    feats = amy.decomposition_features(ghi, hourly["sunshine_min"], hourly["ghi_kt_std"], solar)
    daylight = (solar["zenith"] < amy._MAX_DECOMPOSE_ZENITH) & (ghi > 10.0)
    feats["kd"] = (hourly["dhi_Wm2"].clip(lower=0) / ghi).clip(0.0, 1.0)
    feats["ghi"] = ghi
    feats["dhi"] = hourly["dhi_Wm2"].clip(lower=0)
    feats["station"] = station
    return feats[daylight & feats["kd"].notna() & feats["S"].notna()]


def fit_grid(train: pd.DataFrame, names):
    from sklearn.ensemble import HistGradientBoostingRegressor

    frame = train.dropna(subset=list(names))
    model = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, random_state=0)
    model.fit(frame[list(names)], frame["kd"])
    mesh = np.array(list(itertools.product(*[AXES[n] for n in names])))
    values = np.clip(model.predict(pd.DataFrame(mesh, columns=list(names))), 0.0, 1.0)
    return pd.DataFrame(mesh, columns=list(names)).assign(kd=values)


def score(table: pd.DataFrame, test: pd.DataFrame, names, label: str) -> None:
    from scipy.interpolate import RegularGridInterpolator

    axes = [np.sort(table[n].unique()) for n in names]
    values = table.sort_values(list(names))["kd"].to_numpy().reshape([len(a) for a in axes])
    interp = RegularGridInterpolator(axes, values, bounds_error=False, fill_value=None)
    frame = test.dropna(subset=list(names))
    pts = np.column_stack([frame[n].clip(lower=ax[0], upper=ax[-1]) for n, ax in zip(names, axes)])
    pred = np.clip(interp(pts), 0, 1) * frame["ghi"].to_numpy()
    err = pred - frame["dhi"].to_numpy()
    rrmse = 100 * np.sqrt(np.mean(err ** 2)) / frame["dhi"].mean()
    print(f"  {label}: rRMSE {rrmse:.1f}% of mean hourly diffuse, bias {err.mean():+.1f} W/m2, "
          f"annual sum {100 * pred.sum() / frame['dhi'].sum() - 100:+.1f}%, n={len(frame)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stations-csv", required=True, help="ogd-smn_meta_stations.csv")
    parser.add_argument("--station", action="append", required=True, metavar="ABBR=CSV",
                        help="station abbreviation and its 10-minute CSV with diffuse radiation (repeatable)")
    parser.add_argument("--holdout", type=int, default=None,
                        help="fit on the first station before this year, report error on all stations in it")
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    frames = []
    for item in args.station:
        abbr, path = item.split("=", 1)
        frames.append(station_features(path, args.stations_csv, abbr))
    data = pd.concat(frames)
    print(f"{len(data)} usable station-hours from {', '.join(data['station'].unique())}")

    if args.holdout:
        first = data["station"].iloc[0]
        train = data[(data["station"] == first) & (data.index.year < args.holdout)]
        tables = {"kssd": fit_grid(train, ("kt", "S", "sd", "zen")), "ks": fit_grid(train, ("kt", "S", "zen"))}
        print(f"fitted on {first} before {args.holdout}; held out {args.holdout}:")
        test = data[data.index.year == args.holdout]
        for station, part in test.groupby("station"):
            score(tables["kssd"], part, ("kt", "S", "sd", "zen"), f"{station} hourly+10min (kssd)")
            score(tables["ks"], part, ("kt", "S", "zen"), f"{station} hourly (ks)")
        return

    tables = [
        fit_grid(data, ("kt", "S", "sd", "zen")).assign(table="kssd"),
        fit_grid(data, ("kt", "S", "zen")).assign(table="ks"),
    ]
    out = pd.concat(tables, ignore_index=True)
    for name in ("kt", "S", "sd", "zen", "kd"):
        out[name] = out[name].astype("float32")
    out.to_parquet(args.output, index=False)
    print(f"wrote {args.output} ({len(out)} rows)")


if __name__ == "__main__":
    main()
