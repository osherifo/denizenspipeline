"""fmriflow — Plugin-based neuroscience encoding model pipeline."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("fmriflow")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from fmriflow.pipeline import Pipeline

__all__ = ["Pipeline", "__version__"]
