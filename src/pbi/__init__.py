"""PBI Report Builder - CLI tool for editing Power BI PBIP project files."""

from importlib.metadata import PackageNotFoundError, version as _package_version

try:
    # The version comes from the git tag at build time (hatch-vcs), so a
    # release only needs a tag, never a manifest edit.
    __version__ = _package_version("pbi-report-builder")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0+unknown"
