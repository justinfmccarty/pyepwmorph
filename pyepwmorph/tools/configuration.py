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
    'Clouds and Radiation': ['clt', 'rsds'],
}

VARIABLE_DEPENDENCIES = {
    'Humidity': ['Temperature', 'Pressure'],
    'Dew Point': ['Temperature', 'Humidity', 'Pressure'],
}

#: The order variables must be morphed in so that every variable sees its
#: dependencies already morphed.  Pressure and temperature feed humidity,
#: which in turn feeds dew point.
MORPH_ORDER = ['Pressure', 'Temperature', 'Humidity', 'Dew Point', 'Wind', 'Clouds and Radiation']


def resolve_variable_order(user_variables):
    """Expand variable dependencies and return them in a safe morphing order.

    Dependencies are pulled in transitively, so asking for ``Dew Point``
    alone yields pressure, temperature, humidity, and dew point.  Every
    resolved variable is written to the morphed EPW, which keeps the output
    file internally consistent.

    Parameters
    ----------
    user_variables : list[str]
        The variables the caller asked for.

    Returns
    -------
    list[str]
        Supported variables, deduplicated and ordered for morphing.
    """
    resolved = set()
    pending = list(user_variables)
    while pending:
        variable = pending.pop()
        if variable in resolved:
            continue
        resolved.add(variable)
        pending.extend(VARIABLE_DEPENDENCIES.get(variable, []))

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
        ``"cmip6"`` (default) or ``"custom"``.
    custom_data : dict or None
        When *data_source* is ``"custom"``, a nested dict:
        ``{scenario_label: {variable: csv_path, ...}, ...}``.
        Must include a ``"reference"`` scenario and at least one target.
    reference_scenario : str or None
        Which scenario key to treat as the baseline/reference.
        Defaults to ``"historical"`` for CMIP6, ``"reference"`` for custom.

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
        if target_years is None:
            raise ValueError("target_years (or future_years) must be provided")

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
        else:
            self.reference_scenario = "historical"

        self.model_pathways: list[str] = []
        self.model_variables: list[str] = []
        self.resolved_variables: list[str] = []

        if output_directory is not None:
            self.output_directory = output_directory
            Path(self.output_directory).mkdir(parents=True, exist_ok=True)
        else:
            self.output_directory = None

        self.assign_from_epw()
        self.assign_model_variables()
        self.assign_model_pathways()

    def assign_from_epw(self):
        self.location['latitude'] = self.epw.location['latitude']
        self.location['longitude'] = self.epw.location['longitude']
        self.location['elevation'] = self.epw.location['elevation']
        self.location['utc_offset'] = self.epw.location['utc_offset']
        if self.baseline_range is None:
            self.baseline_range = self.epw.detect_baseline_range()

    def assign_model_variables(self):
        """Resolve user-facing variable names to CMIP6-style variable IDs."""
        self.resolved_variables = resolve_variable_order(self.user_variables)

        model_variables = []
        for variable in self.resolved_variables:
            model_variables.extend(VARIABLE_MAPPING.get(variable, []))

        self.model_variables = sorted(set(model_variables))
        logger.debug("Resolved model variables: %s", self.model_variables)

    def assign_model_pathways(self):
        """Resolve user-facing pathway labels to model experiment IDs.

        For ``data_source="cmip6"``, maps friendly names to SSP IDs.
        For ``data_source="custom"``, passes labels through directly
        and adds the reference scenario.
        """
        self.model_pathways = []

        if self.data_source == "custom":
            self.model_pathways = list(self.custom_data.keys())
            if self.reference_scenario not in self.model_pathways:
                raise ValueError(
                    f"Reference scenario '{self.reference_scenario}' not found "
                    f"in custom_data keys: {self.model_pathways}"
                )
        else:
            for user_path in self.user_pathways:
                if user_path in CMIP6_PATHWAY_MAP:
                    self.model_pathways += CMIP6_PATHWAY_MAP[user_path]
                else:
                    logger.warning("Unknown pathway '%s' -- passing through as-is", user_path)
                    self.model_pathways.append(user_path)
            self.model_pathways = list(set(self.model_pathways))
