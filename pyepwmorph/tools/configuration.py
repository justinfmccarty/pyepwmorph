"""Configuration object used throughout the morphing pipeline."""

import logging
import warnings
from pathlib import Path

from pyepwmorph.tools import io as morpher_io

logger = logging.getLogger(__name__)

__author__ = "Justin McCarty"
__copyright__ = "Copyright 2023-2026"
__credits__ = ["Justin McCarty"]
__license__ = "MIT"
__maintainer__ = "Justin McCarty"
__email__ = "mccarty.justin.f@gmail.com"
__status__ = "Production"

CMIP6_PATHWAY_MAP = {
    'Best Case Scenario': ['historical', 'ssp126'],
    'Middle of the Road': ['historical', 'ssp245'],
    'Upper Middle Scenario': ['historical', 'ssp370'],
    'Worst Case Scenario': ['historical', 'ssp585'],
}

VARIABLE_MAPPING = {
    'Temperature': ['tas', 'tasmax', 'tasmin'],
    'Humidity': ['huss'],
    'Pressure': ['psl'],
    'Wind': ['uas', 'vas'],
    'Radiation': ['rsds'],
    'Clouds and Radiation': ['clt', 'rsds'],
}

#: CH2025 station scenarios carry relative humidity and scalar wind speed
#: directly, and they do not include pressure or cloud cover.
CH2025_PATHWAY_MAP = {
    'GWL 1.5': 'gwl1.5',
    'GWL 2.0': 'gwl2.0',
    'GWL 2.5': 'gwl2.5',
    'GWL 3.0': 'gwl3.0',
}

CH2025_VARIABLE_MAPPING = {
    'Temperature': ['tas', 'tasmax', 'tasmin'],
    'Humidity': ['hurs'],
    'Wind': ['sfcWind'],
    'Radiation': ['rsds'],
    'Dew Point': [],
}

CH2025_UNSUPPORTED = frozenset({'Pressure', 'Clouds and Radiation'})

VARIABLE_DEPENDENCIES = {
    'Humidity': ['Temperature', 'Pressure'],
    'Dew Point': ['Temperature', 'Humidity', 'Pressure'],
}

CH2025_VARIABLE_DEPENDENCIES = {
    'Dew Point': ['Temperature', 'Humidity'],
}

#: The order variables must be morphed in so that every variable sees its
#: dependencies already morphed.  Pressure and temperature feed humidity,
#: which in turn feeds dew point.  ``Radiation`` morphs the solar fields
#: without touching sky cover.
MORPH_ORDER = [
    'Pressure', 'Temperature', 'Humidity', 'Dew Point', 'Wind',
    'Radiation', 'Clouds and Radiation',
]


def _dependencies_for(data_source):
    if data_source == "ch2025":
        return CH2025_VARIABLE_DEPENDENCIES
    return VARIABLE_DEPENDENCIES


def resolve_variable_order(user_variables, data_source="cmip6"):
    """Expand variable dependencies and return them in a safe morphing order.

    Dependencies are pulled in transitively, so asking for ``Dew Point``
    alone yields pressure, temperature, humidity, and dew point.  Every
    resolved variable is written to the morphed EPW, which keeps the output
    file internally consistent.

    For ``data_source="ch2025"`` humidity is a direct relative-humidity
    stretch, so it has no dependencies, and dew point needs only temperature
    and humidity.

    Parameters
    ----------
    user_variables : list[str]
        The variables the caller asked for.
    data_source : str
        ``"cmip6"`` (default), ``"custom"``, or ``"ch2025"``.

    Returns
    -------
    list[str]
        Supported variables, deduplicated and ordered for morphing.
    """
    dependencies = _dependencies_for(data_source)
    resolved = set()
    pending = list(user_variables)
    while pending:
        variable = pending.pop()
        if variable in resolved:
            continue
        resolved.add(variable)
        pending.extend(dependencies.get(variable, []))

    added = resolved - set(user_variables)
    if added:
        logger.info("Added dependencies of the requested variables: %s", ", ".join(sorted(added)))

    unsupported = resolved - set(MORPH_ORDER)
    if unsupported:
        logger.warning("Ignoring unsupported morphing variable(s): %s", ", ".join(sorted(unsupported)))

    return [variable for variable in MORPH_ORDER if variable in resolved]


class MorphConfig:
    """Hold and transfer configuration settings for the morphing pipeline.

    Parameters
    ----------
    project_name : str
        Name for this morphing project.
    epw_fp : str
        File path to the base EPW file.
    user_variables : list[str]
        Variables to morph (e.g. ``['Temperature', 'Humidity']``).
    user_pathways : list[str] or str
        Scenario pathway labels.  For CMIP6 these are the friendly names
        (e.g. ``'Best Case Scenario'``).  For custom data these are
        arbitrary labels that must match the keys of ``custom_data``.
    percentiles : list or scalar
        Ensemble percentile(s) to use.
    target_years : list[int]
        Target years for morphing.
    output_directory : str or None
        Where to write morphed EPW files.
    model_sources : list[str] or None
        CMIP6 model source IDs (ignored for custom data).
    baseline_range : tuple[int, int] or None
        ``(start_year, end_year)`` for the baseline period.  If *None*,
        derived from the EPW file.
    data_source : str
        ``"cmip6"`` (default), ``"custom"``, or ``"ch2025"``.
    custom_data : dict or None
        When *data_source* is ``"custom"``, a nested dict:
        ``{scenario_label: {variable: csv_path, ...}, ...}``.
        Must include a ``"reference"`` scenario and at least one target.
    reference_scenario : str or None
        Which scenario key to treat as the baseline/reference.
        Defaults to ``"historical"`` for CMIP6, ``"reference"`` for custom,
        and ``"ref91-20"`` for CH2025.
    ch2025_full_coverage : bool
        CH2025 only. When True, match the site only against stations that
        carry every CH2025 variable, so the station does not change with the
        variables requested. Default False matches against stations that
        carry the requested variables.

    Attributes
    ----------
    ch2025_station : pd.Series or None
        CH2025 only. The matched station row, including ``distance_km``,
        ``elevation_difference_m`` and ``weak_match``.
    ch2025_notes : list[str]
        CH2025 only. Plain-language caveats about this morph (baseline
        mismatch, weak station match), for display to users.

    Backward Compatibility
    ----------------------
    The ``future_years`` parameter is accepted as an alias for
    ``target_years``.
    """

    def __init__(
        self,
        project_name,
        epw_fp,
        user_variables,
        user_pathways,
        percentiles,
        target_years=None,
        output_directory=None,
        model_sources=None,
        baseline_range=None,
        data_source="cmip6",
        custom_data=None,
        reference_scenario=None,
        ch2025_full_coverage=False,
        # backward-compat alias
        future_years=None,
    ):
        if target_years is None and future_years is not None:
            warnings.warn(
                "future_years is deprecated, use target_years instead",
                DeprecationWarning,
                stacklevel=2,
            )
            target_years = future_years
        if target_years is None and data_source != "ch2025":
            raise ValueError("target_years (or future_years) must be provided")
        if data_source == "ch2025" and target_years is None:
            target_years = []

        if model_sources is None:
            model_sources = ['ACCESS-CM2', 'CanESM5', 'TaiESM1']

        self.project_name = project_name
        self.epw = morpher_io.Epw(epw_fp)
        self.model_sources = model_sources
        self.user_variables = user_variables
        self.data_source = data_source
        self.custom_data = custom_data or {}

        if isinstance(user_pathways, list):
            self.user_pathways = user_pathways
        else:
            self.user_pathways = [user_pathways]

        if isinstance(percentiles, list):
            self.percentiles = percentiles
        else:
            self.percentiles = [percentiles]

        self.location = {
            'latitude': None,
            'longitude': None,
            'elevation': None,
            'utc_offset': None,
        }
        self.baseline_range = baseline_range
        self.target_years = target_years
        # backward-compat property
        self.future_years = self.target_years

        if reference_scenario is not None:
            self.reference_scenario = reference_scenario
        elif data_source == "custom":
            self.reference_scenario = "reference"
        elif data_source == "ch2025":
            self.reference_scenario = "ref91-20"
        else:
            self.reference_scenario = "historical"

        self.model_pathways: list[str] = []
        self.model_variables: list[str] = []
        self.resolved_variables: list[str] = []
        self.ch2025_station = None
        self.ch2025_notes: list[str] = []
        self.ch2025_full_coverage = bool(ch2025_full_coverage)

        if output_directory is not None:
            self.output_directory = output_directory
            Path(self.output_directory).mkdir(parents=True, exist_ok=True)
        else:
            self.output_directory = None

        self.assign_from_epw()
        self.assign_model_variables()
        self.assign_ch2025_station()
        self.assign_model_pathways()

    def assign_from_epw(self):
        self.location['latitude'] = self.epw.location['latitude']
        self.location['longitude'] = self.epw.location['longitude']
        self.location['elevation'] = self.epw.location['elevation']
        self.location['utc_offset'] = self.epw.location['utc_offset']
        if self.baseline_range is None:
            self.baseline_range = self.epw.detect_baseline_range()

        if self.data_source == "ch2025":
            from pyepwmorph.models.ch2025 import (
                CH2025_BASELINE_RANGE,
                CH2025_BBOX,
                baseline_matches,
                in_switzerland,
            )

            latitude = self.location['latitude']
            longitude = self.location['longitude']
            if not in_switzerland(latitude, longitude):
                west, south, east, north = CH2025_BBOX
                raise ValueError(
                    f"EPW location ({latitude}, {longitude}) is outside Switzerland. "
                    f"CH2025 covers longitude {west} to {east} and latitude {south} to {north}. "
                    f"Use data_source='cmip6' for locations outside that domain."
                )
            if not baseline_matches(self.baseline_range):
                start, end = (int(year) for year in self.baseline_range)
                ref_start, ref_end = CH2025_BASELINE_RANGE
                if end > ref_end:
                    effect = (
                        f"Years after {ref_end} already contain part of that warming, "
                        f"so the morphed file may overstate it."
                    )
                else:
                    effect = (
                        f"Years before {ref_start} were cooler, so the morphed file may "
                        f"understate the warming."
                    )
                note = (
                    f"The EPW covers {start}-{end} but CH2025 changes are measured from "
                    f"{ref_start}-{ref_end}. {effect} For CH2025, use a TMY built from "
                    f"{ref_start}-{ref_end} data."
                )
                self.ch2025_notes.append(note)
                warnings.warn(note, UserWarning, stacklevel=2)

    def assign_model_variables(self):
        """Resolve user-facing variable names to model variable IDs."""
        if self.data_source == "ch2025":
            blocked = set(self.user_variables) & CH2025_UNSUPPORTED
            if blocked:
                names = ", ".join(sorted(blocked))
                raise ValueError(
                    f"CH2025 station scenarios do not include {names}. "
                    f"Use data_source='cmip6' for pressure and cloud cover, "
                    f"or request Radiation instead of Clouds and Radiation."
                )
            mapping = CH2025_VARIABLE_MAPPING
        else:
            mapping = VARIABLE_MAPPING

        self.resolved_variables = resolve_variable_order(self.user_variables, self.data_source)

        model_variables = []
        for variable in self.resolved_variables:
            model_variables.extend(mapping.get(variable, []))

        self.model_variables = sorted(set(model_variables))
        logger.debug("Resolved model variables: %s", self.model_variables)

    def assign_ch2025_station(self):
        """Match the EPW site to a CH2025 station that has the requested variables."""
        if self.data_source != "ch2025":
            return
        from pyepwmorph.models.ch2025 import CH2025_VARIABLES, nearest_station

        variables = sorted(CH2025_VARIABLES) if self.ch2025_full_coverage else self.model_variables
        station = nearest_station(
            self.location['latitude'],
            self.location['longitude'],
            self.location['elevation'],
            variables=variables,
        )
        self.ch2025_station = station
        if station["weak_match"]:
            self.ch2025_notes.append(
                f"The nearest suitable CH2025 station, {station['name']}, is "
                f"{station['distance_km']:.0f} km away and "
                f"{station['elevation_difference_m']:+.0f} m in elevation. Its climate "
                f"signal may not represent this site."
            )

    def assign_model_pathways(self):
        """Resolve user-facing pathway labels to model experiment IDs.

        For ``data_source="cmip6"``, maps friendly names to SSP IDs.
        For ``data_source="custom"``, passes labels through directly
        and adds the reference scenario.
        For ``data_source="ch2025"``, maps warming-level labels to state ids
        and always includes the ``ref91-20`` reference.
        """
        self.model_pathways = []

        if self.data_source == "custom":
            self.model_pathways = list(self.custom_data.keys())
            if self.reference_scenario not in self.model_pathways:
                raise ValueError(
                    f"Reference scenario '{self.reference_scenario}' not found "
                    f"in custom_data keys: {self.model_pathways}"
                )
        elif self.data_source == "ch2025":
            known = set(CH2025_PATHWAY_MAP.values())
            for user_path in self.user_pathways:
                if user_path in CH2025_PATHWAY_MAP:
                    self.model_pathways.append(CH2025_PATHWAY_MAP[user_path])
                elif user_path in known:
                    self.model_pathways.append(user_path)
                else:
                    raise ValueError(
                        f"Unknown CH2025 warming level '{user_path}'. "
                        f"Use one of {list(CH2025_PATHWAY_MAP)} or {sorted(known)}."
                    )
            if self.reference_scenario not in self.model_pathways:
                self.model_pathways.append(self.reference_scenario)
        else:
            for user_path in self.user_pathways:
                if user_path in CMIP6_PATHWAY_MAP:
                    self.model_pathways += CMIP6_PATHWAY_MAP[user_path]
                else:
                    logger.warning("Unknown pathway '%s' -- passing through as-is", user_path)
                    self.model_pathways.append(user_path)
            self.model_pathways = list(set(self.model_pathways))
