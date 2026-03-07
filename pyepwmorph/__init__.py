"""pyepwmorph -- Climate model data gathering and EPW file morphing."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("pyepwmorph")
except PackageNotFoundError:
    __version__ = "2.0.0"
