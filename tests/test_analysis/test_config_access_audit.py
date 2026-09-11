"""Which top-level config sections each built-in module reads.

Graph nodes get a config where only their own section holds their params.
Modules compiled from fixed-stage YAML also keep the full config as graph
globals, so a module that reads another stage's section still works there,
but a graph built node by node must provide that section explicitly. This
test keeps that coupling visible: reading a section a module's category does
not own fails here until it is added to ``DOCUMENTED_COUPLING`` with a reason.
"""

from __future__ import annotations

import pathlib
import re

MODULES = pathlib.Path(__file__).resolve().parents[2] / "fmriflow" / "modules"

# Top-level keys of a subject / group / study config.
SECTIONS = {
    "experiment", "subject", "subject_config", "paths", "stimulus", "response", "features",
    "preparation", "split", "model", "analysis", "reporting", "intermediates", "qa", "checkpoint",
    "group_analyze", "group_report", "study_analyze", "study_report", "output_dir",
}
GLOBALS = {"experiment", "subject", "subject_config", "paths", "intermediates", "qa"}
OWNED = {
    "stimulus_loaders": {"stimulus"},
    "response_loaders": {"response"},
    "preparers": {"preparation", "split"},
    "models": {"model"},
    "analyzers": {"analysis"},
    "reporters": {"reporting"},
    "group_analyzers": {"group_analyze", "group_report", "output_dir"},
    "group_reporters": {"group_analyze", "group_report", "output_dir"},
    "study_analyzers": {"study_analyze", "study_report", "output_dir"},
    "study_reporters": {"study_analyze", "study_report", "output_dir"},
}

DOCUMENTED_COUPLING = {
    # refuses to skip stimuli when a feature still needs to be computed from them
    ("stimulus_loaders", "skip.py", "features"),
    # falls back to preparation delays when the model block has none
    ("models", "himalaya.py", "preparation"),
    # rebuilds delayed predictions using the model's delays
    ("analyzers", "block_permutation_significance.py", "model"),
    # reads the response space to pick the fsaverage masks
    ("reporters", "nsd_fsaverage_flatmap.py", "response"),
}

_ACCESS = re.compile(r"\b(?:config|cfg|full_config)\s*(?:\.get\(\s*|\[\s*)[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']")


def _cross_section_reads() -> set[tuple[str, str, str]]:
    found = set()
    for category, owned in OWNED.items():
        for path in sorted((MODULES / category).glob("*.py")):
            if path.name.startswith("__"):
                continue
            for section in set(_ACCESS.findall(path.read_text())):
                if section in SECTIONS and section not in owned and section not in GLOBALS:
                    found.add((category, path.name, section))
    return found


def test_cross_section_config_reads_are_documented():
    undocumented = _cross_section_reads() - DOCUMENTED_COUPLING
    assert not undocumented, (
        "modules read config sections their category does not own; document them in "
        f"DOCUMENTED_COUPLING or pass the value as a param/input: {sorted(undocumented)}")


def test_documented_coupling_is_still_real():
    stale = DOCUMENTED_COUPLING - _cross_section_reads()
    assert not stale, f"no longer read, remove from DOCUMENTED_COUPLING: {sorted(stale)}"
