"""What the heuristic did: every DICOM series in, every BIDS file out.

A conversion is a lossy decision. The heuristic looks at N scanner series and
claims some of them for BIDS outputs; whatever it does not claim is silently
discarded, and nothing surfaced that. The discarded set is often the
interesting one — an MP2RAGE protocol emits INV1, INV2 and UNI per repetition,
and a heuristic that keeps only UNI throws away exactly the volumes needed to
correct the image later.

Everything needed is already on disk. heudiconv writes, under
``<bids_dir>/.heudiconv/<subject>/info/``:

- ``dicominfo.tsv`` — one row per input series, with description, file count,
  dimensions, TR/TE and more.
- ``<subject>.auto.txt`` — a repr of the heuristic's ``infotodict`` result,
  mapping each output template to the series ids it claimed.

Joining them on ``series_id`` reconstructs the decision table. This module is
pure derivation: it runs after the fact, changes nothing, and needs no
cooperation from the heuristic.

Note the limit that implies. heudiconv records what the heuristic *claimed*,
never why it passed over the rest, so an unclaimed series is reported as
dropped without a reason. A real reason needs the heuristic to say so itself.
"""

from __future__ import annotations

import ast
import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

HEUDICONV_DIR = ".heudiconv"

# dicominfo columns worth carrying to the UI. The file has ~30; most are
# scanner bookkeeping that would only crowd the table.
_SERIES_FIELDS = (
    "series_id", "series_description", "protocol_name", "sequence_name",
    "series_files", "dim1", "dim2", "dim3", "dim4", "TR", "TE",
    "is_derived", "is_motion_corrected",
)


class DecisionTableError(RuntimeError):
    """Raised when a conversion's provenance cannot be read."""


@dataclass
class SeriesDecision:
    """One input series and what became of it."""

    series_id: str
    description: str
    protocol: str
    n_files: int
    dims: list[int]
    tr: float | None
    te: float | None
    is_derived: bool
    # None when the heuristic did not claim this series.
    output_template: str | None = None

    @property
    def dropped(self) -> bool:
        return self.output_template is None

    def to_dict(self) -> dict:
        return {
            "series_id": self.series_id,
            "description": self.description,
            "protocol": self.protocol,
            "n_files": self.n_files,
            "dims": self.dims,
            "tr": self.tr,
            "te": self.te,
            "is_derived": self.is_derived,
            "output_template": self.output_template,
            "dropped": self.dropped,
        }


@dataclass
class DecisionTable:
    subject: str
    bids_dir: str
    series: list[SeriesDecision] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def n_mapped(self) -> int:
        return sum(1 for s in self.series if not s.dropped)

    @property
    def n_dropped(self) -> int:
        return sum(1 for s in self.series if s.dropped)

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "bids_dir": self.bids_dir,
            "n_series": len(self.series),
            "n_mapped": self.n_mapped,
            "n_dropped": self.n_dropped,
            "series": [s.to_dict() for s in self.series],
            "warnings": self.warnings,
        }


# ── reading heudiconv's provenance ───────────────────────────────────

def info_dir(bids_dir: Path | str, subject: str) -> Path:
    """``<bids_dir>/.heudiconv/<subject>/info`` — subject may carry ``sub-``."""
    label = subject[4:] if subject.startswith("sub-") else subject
    return Path(bids_dir) / HEUDICONV_DIR / label / "info"


def _read_series(info: Path) -> list[dict]:
    path = info / "dicominfo.tsv"
    if not path.is_file():
        raise DecisionTableError(
            f"no dicominfo.tsv under {info} — this dataset was not produced by "
            "heudiconv, or its .heudiconv directory was removed"
        )
    with open(path, newline="") as f:
        return [
            {k: row.get(k, "") for k in _SERIES_FIELDS}
            for row in csv.DictReader(f, delimiter="\t")
        ]


def _read_mapping(info: Path, subject: str) -> dict[str, str]:
    """series_id -> output template, from ``<subject>.auto.txt``.

    The file is a plain ``repr`` of heudiconv's info dict, whose keys are
    ``(template, outtype, annotation)`` tuples — hence ``literal_eval`` rather
    than json.
    """
    label = subject[4:] if subject.startswith("sub-") else subject
    candidates = [info / f"{label}.auto.txt", info / f"{label}.edit.txt"]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        raise DecisionTableError(
            f"no {label}.auto.txt under {info} — the conversion left no "
            "record of what the heuristic mapped"
        )

    try:
        raw = ast.literal_eval(path.read_text())
    except (ValueError, SyntaxError) as e:
        raise DecisionTableError(f"could not parse {path}: {e}") from e

    out: dict[str, str] = {}
    for key, series_ids in (raw or {}).items():
        template = key[0] if isinstance(key, tuple) else str(key)
        for sid in series_ids or ():
            out[str(sid)] = str(template)
    return out


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── the checks ───────────────────────────────────────────────────────

def _warnings_for(series: list[SeriesDecision]) -> list[str]:
    """Findings worth surfacing without the reader having to spot them.

    Every check here keys off a concrete property, never off how similar two
    descriptions look. An earlier version compared normalised descriptions and
    fired on correct conversions, because run indices sit mid-string
    (``run-01_INV1`` vs ``run-02_INV1``) — and normalising hard enough to fix
    that also collapsed ``INV1`` into ``INV2``, hiding the very mistake it was
    meant to catch. A check that cries wolf on good data trains people to
    ignore it.
    """
    out: list[str] = []

    by_template: dict[str, list[SeriesDecision]] = {}
    for s in series:
        if s.output_template:
            by_template.setdefault(s.output_template, []).append(s)

    for template, claimed in by_template.items():
        name = template.split("/")[-1]

        # Several series per template is normal — that is what {item} is for.
        # Mixing scanner-original with scanner-derived images into one output
        # is not: an MP2RAGE emits ORIGINAL inversions and a DERIVED uniform
        # image, and collapsing them yields several "T1w" volumes that a
        # preprocessor will try to average.
        if len({s.is_derived for s in claimed}) > 1:
            derived = [s.description for s in claimed if s.is_derived]
            original = [s.description for s in claimed if not s.is_derived]
            out.append(
                f"'{name}' claims both scanner-derived and original series — "
                f"derived: {', '.join(sorted(derived))}; "
                f"original: {', '.join(sorted(original))}. These are usually "
                f"different images, not repeats."
            )

        # Repeats of one acquisition share a geometry. Differing dimensions
        # mean distinct images landed in one output.
        geometries = {tuple(s.dims) for s in claimed}
        if len(geometries) > 1:
            out.append(
                f"'{name}' claims series with differing dimensions "
                f"({'; '.join('×'.join(str(d) for d in g if d) for g in sorted(geometries))}) "
                f"— repeats of one acquisition should share a geometry."
            )

    # A dropped series carrying real image data is worth a second look; a
    # 3-file localizer is not.
    substantial = [s for s in series if s.dropped and s.n_files >= 20]
    if substantial:
        out.append(
            f"{len(substantial)} dropped series carry ≥20 files each and may "
            f"hold usable data: "
            + ", ".join(f"{s.description} ({s.n_files})" for s in substantial)
        )

    if series and not any(not s.dropped for s in series):
        out.append("no series were mapped — the heuristic matched nothing")

    return out


# ── entry point ──────────────────────────────────────────────────────

def build_decision_table(bids_dir: Path | str, subject: str) -> DecisionTable:
    """Reconstruct what the heuristic did, from files heudiconv left behind."""
    info = info_dir(bids_dir, subject)
    rows = _read_series(info)
    mapping = _read_mapping(info, subject)

    series = [
        SeriesDecision(
            series_id=r["series_id"],
            description=r["series_description"],
            protocol=r["protocol_name"],
            n_files=_to_int(r["series_files"]),
            dims=[_to_int(r[d]) for d in ("dim1", "dim2", "dim3", "dim4")],
            tr=_to_float(r["TR"]),
            te=_to_float(r["TE"]),
            is_derived=str(r["is_derived"]).strip().lower() in ("true", "1", "yes"),
            output_template=mapping.get(r["series_id"]),
        )
        for r in rows
    ]

    table = DecisionTable(
        subject=subject, bids_dir=str(bids_dir), series=series,
    )
    table.warnings = _warnings_for(series)
    logger.info(
        "decision table for %s: %d series, %d mapped, %d dropped",
        subject, len(series), table.n_mapped, table.n_dropped,
    )
    return table


def has_provenance(bids_dir: Path | str, subject: str) -> bool:
    """True when a decision table can be built — lets the UI hide the panel."""
    info = info_dir(bids_dir, subject)
    label = subject[4:] if subject.startswith("sub-") else subject
    return (info / "dicominfo.tsv").is_file() and (
        (info / f"{label}.auto.txt").is_file() or (info / f"{label}.edit.txt").is_file()
    )
