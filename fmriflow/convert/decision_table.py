"""What the heuristic did: every DICOM series in, every BIDS file out.

A conversion is a lossy decision. The heuristic looks at N scanner series and
claims some of them for BIDS outputs; whatever it does not claim is silently
discarded, and nothing surfaced that. The discarded set is often the
interesting one — an MP2RAGE protocol emits INV1, INV2 and UNI per repetition,
and a heuristic that keeps only UNI throws away exactly the volumes needed to
correct the image later.

Two views come out of the same join, answering different questions:

- **audit** (per subject) — one row per series, with the parameters a rule
  discriminates on (TR/TE/dims/image_type) beside the BIDS path it produced.
  This is the debugging view: you need the parameters and the outcome in one
  row to see *why* a rule fired.
- **flow** (per study) — aggregated protocol → datatype → suffix counts, for a
  Sankey. Aggregate only; at series granularity it is spaghetti. Its one job
  is making the dropped ribbon impossible to ignore.

Everything is derived from what heudiconv already leaves behind, under
``<bids_dir>/.heudiconv/<subject>/info/``:

- ``dicominfo.tsv`` — one row per input series.
- ``<subject>.auto.txt`` — a repr of the heuristic's ``infotodict`` result,
  mapping each output template to the series ids it claimed.

So this runs after the fact, changes nothing, and needs no cooperation from the
heuristic. The limit that implies: heudiconv records what the heuristic
*claimed*, never why it passed over the rest, so an unclaimed series is
reported as dropped without a reason.
"""

from __future__ import annotations

import ast
import csv
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

HEUDICONV_DIR = ".heudiconv"

_SERIES_FIELDS = (
    "series_id", "series_description", "protocol_name", "sequence_name",
    "series_files", "dim1", "dim2", "dim3", "dim4", "TR", "TE",
    "is_derived", "is_motion_corrected", "image_type",
)


class DecisionTableError(RuntimeError):
    """Raised when a conversion's provenance cannot be read."""


# ── per-series record ────────────────────────────────────────────────

@dataclass
class SeriesDecision:
    """One input series and everything needed to judge the rule that fired.

    TR/TE/dims/image_type sit on the same row deliberately: when a heuristic
    misfires you need the parameters it discriminated on right beside the
    outcome, or you are cross-referencing two tables to answer one question.
    """

    series_number: int
    series_id: str
    description: str
    protocol: str
    sequence: str
    n_files: int
    dims: list[int]
    tr: float | None
    te: float | None
    is_derived: bool
    image_type: list[str]
    # A series can be claimed by SEVERAL templates — a GRE fieldmap fans out
    # to magnitude1, magnitude2 and phasediff. Keeping only one would hide
    # exactly the case worth seeing.
    outputs: list[str] = field(default_factory=list)   # resolved BIDS paths
    rules: list[str] = field(default_factory=list)     # matched templates

    @property
    def dropped(self) -> bool:
        return not self.rules

    @property
    def status(self) -> str:
        if self.dropped:
            return "dropped"
        return f"fan-out ×{len(self.rules)}" if len(self.rules) > 1 else "ok"

    def to_dict(self) -> dict:
        return {
            "series_number": self.series_number,
            "series_id": self.series_id,
            "description": self.description,
            "protocol": self.protocol,
            "sequence": self.sequence,
            "n_files": self.n_files,
            "dims": self.dims,
            "tr": self.tr,
            "te": self.te,
            "is_derived": self.is_derived,
            "image_type": self.image_type,
            "outputs": self.outputs,
            "rules": self.rules,
            "dropped": self.dropped,
            "status": self.status,
        }


@dataclass
class DecisionTable:
    subject: str
    bids_dir: str
    session: str | None = None
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
            "session": self.session,
            "bids_dir": self.bids_dir,
            "n_series": len(self.series),
            "n_mapped": self.n_mapped,
            "n_dropped": self.n_dropped,
            "series": [s.to_dict() for s in self.series],
            "warnings": self.warnings,
        }


# ── reading heudiconv's provenance ───────────────────────────────────

def _label(subject: str) -> str:
    return subject[4:] if subject.startswith("sub-") else subject



def _dicominfo(info: Path) -> Path | None:
    """heudiconv writes ``dicominfo.tsv`` sessionless and ``dicominfo_ses-<ses>.tsv``
    for a sessioned conversion."""
    flat = info / "dicominfo.tsv"
    if flat.is_file():
        return flat
    return next(iter(sorted(info.glob("dicominfo_ses-*.tsv"))), None)


def _mapping_file(info: Path, label: str) -> Path | None:
    """``<sub>.auto.txt`` (or a hand-edited ``.edit.txt``); sessioned runs get
    ``<sub>_ses-<ses>.auto.txt``. The edit file wins when both exist."""
    for pattern in (f"{label}.edit.txt", f"{label}_ses-*.edit.txt", f"{label}.auto.txt", f"{label}_ses-*.auto.txt"):
        found = sorted(info.glob(pattern)) if "*" in pattern else ([info / pattern] if (info / pattern).is_file() else [])
        if found:
            return found[0]
    return None


def info_dir(bids_dir: Path | str, subject: str, session: str | None = None) -> Path:
    """Locate a conversion's ``info`` directory.

    heudiconv writes ``.heudiconv/<sub>/info`` for a sessionless conversion
    and ``.heudiconv/<sub>/ses-<ses>/info`` when a session is given. Looking
    only in the first place makes every sessioned study report "no
    provenance" — a silent miss rather than an error, which is worse.

    With no explicit session, the sessionless path wins if it exists;
    otherwise the first session found is used, so single-session studies work
    without the caller knowing the label.
    """
    root = Path(bids_dir) / HEUDICONV_DIR / _label(subject)
    if session:
        label = session if session.startswith("ses-") else f"ses-{session}"
        return root / label / "info"

    flat = root / "info"
    if _dicominfo(flat) is not None:
        return flat
    for child in sorted(root.glob("ses-*")):
        if _dicominfo(child / "info") is not None:
            return child / "info"
    return flat        # nothing found; caller reports the miss


def list_units(bids_dir: Path | str) -> list[tuple[str, str | None]]:
    """Every (subject, session) with conversion provenance, sorted.

    A sessioned study gets one unit per session rather than one per subject:
    a subject missing an entire session is a gap in its own right.
    """
    root = Path(bids_dir) / HEUDICONV_DIR
    if not root.is_dir():
        return []
    units: list[tuple[str, str | None]] = []
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        if _dicominfo(sub / "info") is not None:
            units.append((sub.name, None))
        for ses in sorted(sub.glob("ses-*")):
            if _dicominfo(ses / "info") is not None:
                units.append((sub.name, ses.name))
    return units


def list_subjects(bids_dir: Path | str) -> list[str]:
    """Subjects with conversion provenance, in sorted order."""
    seen: list[str] = []
    for subject, _ in list_units(bids_dir):
        if subject not in seen:
            seen.append(subject)
    return seen


def unit_label(subject: str, session: str | None) -> str:
    """Row label for a (subject, session) pair."""
    return f"sub-{_label(subject)}" + (f"/{session}" if session else "")


def _read_series(info: Path) -> list[dict]:
    path = _dicominfo(info)
    if path is None:
        raise DecisionTableError(
            f"no dicominfo.tsv (or dicominfo_ses-*.tsv) under {info} — this dataset was not "
            "produced by heudiconv, or its .heudiconv directory was removed"
        )
    with open(path, newline="") as f:
        return [
            {k: row.get(k, "") for k in _SERIES_FIELDS}
            for row in csv.DictReader(f, delimiter="\t")
        ]


def _read_mapping(info: Path, subject: str) -> dict[str, list[tuple[str, int]]]:
    """``{series_id: [(template, item_index), ...]}``.

    The index matters because heudiconv assigns ``{item}`` by position within
    a template's series list, so it is what turns a template back into the
    path actually written.
    """
    label = _label(subject)
    path = _mapping_file(info, label)
    if path is None:
        raise DecisionTableError(
            f"no {label}.auto.txt under {info} — the conversion left no "
            "record of what the heuristic mapped"
        )

    try:
        raw = ast.literal_eval(path.read_text())
    except (ValueError, SyntaxError) as e:
        raise DecisionTableError(f"could not parse {path}: {e}") from e

    out: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for key, series_ids in (raw or {}).items():
        template = key[0] if isinstance(key, tuple) else str(key)
        # {item} counts from 1 within each template, in claim order.
        for index, sid in enumerate(series_ids or (), start=1):
            out[str(sid)].append((str(template), index))
    return out


def declared_templates(info: Path, subject: str) -> list[str]:
    """Every template the heuristic declared, claimed or not.

    A template that produced nothing anywhere is the signal for a rule that
    never matched.
    """
    label = _label(subject)
    path = _mapping_file(info, label)
    if path is None:
        return []
    try:
        raw = ast.literal_eval(path.read_text())
    except (ValueError, SyntaxError):
        return []
    return [str(k[0] if isinstance(k, tuple) else k) for k in (raw or {})]


# ── template resolution ──────────────────────────────────────────────

def resolve_template(template: str, subject: str, item: int) -> str:
    """Fill a heudiconv template into the BIDS path it produced.

    heudiconv substitutes ``{subject}`` and numbers ``{item}`` from 1 within
    each template, so the resolved path is reconstructable without touching
    the output tree.
    """
    out = template.replace("{subject}", _label(subject))
    # {item:02d} and bare {item}
    out = re.sub(r"\{item(?::[^}]*)?\}", lambda m: _format_item(m.group(0), item), out)
    return out


def _format_item(token: str, item: int) -> str:
    m = re.match(r"\{item:(\d*)(\d)d\}", token)
    if m:
        width = int(m.group(1) + m.group(2))
        return str(item).zfill(width)
    return str(item)


def bids_key(path: str) -> str:
    """Collapse a BIDS path to a per-acquisition key.

    Drops only the things that vary by *repetition* — the subject label and
    the run index — and keeps every other entity. ``inv-1`` and ``inv-2`` are
    different images, and a subject missing one of them is a real finding, so
    folding them into a single key would hide exactly that. Run indices do fold, because four runs of one acquisition is not four
    different things to be missing.
    """
    parts = path.split("/")
    datatype = parts[-2] if len(parts) >= 2 else "?"
    name = parts[-1]
    # Order matters: strip run/ses while they still carry their leading
    # underscore, before the sub- prefix is removed and the next entity
    # becomes the start of the string.
    name = re.sub(r"_run-[0-9]+", "", name)
    name = re.sub(r"_ses-[A-Za-z0-9]+", "", name)
    name = re.sub(r"^sub-[A-Za-z0-9]+_", "", name)
    return f"{datatype}/{name}"


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: str) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # heudiconv writes -1 where the tag is absent.
    return None if v < 0 else v


def _parse_image_type(value: str) -> list[str]:
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return [v for v in str(value).split("\\") if v]
    if isinstance(parsed, (list, tuple)):
        return [str(v) for v in parsed]
    return [str(parsed)]


def _series_number(series_id: str) -> int:
    """Leading integer of a heudiconv series id (``4001-anat_...``)."""
    m = re.match(r"(\d+)", series_id or "")
    return int(m.group(1)) if m else 0


# ── the checks ───────────────────────────────────────────────────────

def _warnings_for(series: list[SeriesDecision]) -> list[str]:
    """Findings worth surfacing without the reader having to spot them.

    Every check keys off a concrete property, never off how similar two
    descriptions look. An earlier version compared normalised descriptions and
    fired on correct conversions, because run indices sit mid-string
    (``run-01_INV1`` vs ``run-02_INV1``) — and normalising hard enough to fix
    that also collapsed ``INV1`` into ``INV2``, hiding the very mistake it was
    meant to catch. A check that cries wolf on good data trains people to
    ignore it.
    """
    out: list[str] = []

    by_rule: dict[str, list[SeriesDecision]] = defaultdict(list)
    for s in series:
        for rule in s.rules:
            by_rule[rule].append(s)

    for rule, claimed in by_rule.items():
        name = rule.split("/")[-1]

        # Mixing scanner-original with scanner-derived images into one output
        # is the MP2RAGE trap: ORIGINAL inversions and a DERIVED uniform image
        # collapsed into several "T1w" volumes a preprocessor will average.
        if len({s.is_derived for s in claimed}) > 1:
            derived = sorted(s.description for s in claimed if s.is_derived)
            original = sorted(s.description for s in claimed if not s.is_derived)
            out.append(
                f"'{name}' claims both scanner-derived and original series — "
                f"derived: {', '.join(derived)}; original: {', '.join(original)}. "
                f"These are usually different images, not repeats."
            )

        geometries = {tuple(s.dims) for s in claimed}
        if len(geometries) > 1:
            shown = "; ".join("×".join(str(d) for d in g if d) for g in sorted(geometries))
            out.append(
                f"'{name}' claims series with differing dimensions ({shown}) — "
                f"repeats of one acquisition should share a geometry."
            )

    if series and not any(not s.dropped for s in series):
        out.append("no series were mapped — the heuristic matched nothing")

    return out


# ── view 1: per-subject audit ────────────────────────────────────────

def build_decision_table(
    bids_dir: Path | str, subject: str, session: str | None = None,
) -> DecisionTable:
    """Reconstruct what the heuristic did, from files heudiconv left behind."""
    info = info_dir(bids_dir, subject, session)
    if not session and info.parent.name.startswith("ses-"):
        session = info.parent.name  # the session the fallback picked

    rows = _read_series(info)
    mapping = _read_mapping(info, subject)

    series: list[SeriesDecision] = []
    for r in rows:
        sid = r["series_id"]
        claims = mapping.get(sid, [])
        series.append(SeriesDecision(
            series_number=_series_number(sid),
            series_id=sid,
            description=r["series_description"],
            protocol=r["protocol_name"],
            sequence=r["sequence_name"],
            n_files=_to_int(r["series_files"]),
            dims=[_to_int(r[d]) for d in ("dim1", "dim2", "dim3", "dim4")],
            tr=_to_float(r["TR"]),
            te=_to_float(r["TE"]),
            is_derived=str(r["is_derived"]).strip().lower() in ("true", "1", "yes"),
            image_type=_parse_image_type(r["image_type"]),
            rules=[t for t, _ in claims],
            outputs=[resolve_template(t, subject, i) for t, i in claims],
        ))

    # Ordered by series number: that is the order they came off the scanner,
    # and the order anyone reading a protocol expects.
    series.sort(key=lambda s: (s.series_number, s.series_id))

    # Store the bare label. Callers may pass "01" or "sub-01"; echoing the
    # raw string back means a UI that renders "sub-{subject}" produces
    # "sub-sub-01" for one of them.
    table = DecisionTable(
        subject=_label(subject), session=session,
        bids_dir=str(bids_dir), series=series,
    )
    table.warnings = _warnings_for(series)
    logger.info(
        "decision table for %s: %d series, %d mapped, %d dropped",
        subject, len(series), table.n_mapped, table.n_dropped,
    )
    return table


def has_provenance(
    bids_dir: Path | str, subject: str, session: str | None = None,
) -> bool:
    """True when a decision table can be built — lets the UI hide the panel."""
    info = info_dir(bids_dir, subject, session)
    return _dicominfo(info) is not None and _mapping_file(info, _label(subject)) is not None


# ── view 2: study-level flow ─────────────────────────────────────────

def build_flow(bids_dir: Path | str) -> dict:
    """Aggregated protocol → datatype → suffix link counts, for a Sankey.

    Aggregate on purpose. At series granularity a Sankey is unreadable; its
    one useful job is making the dropped ribbon large enough to be impossible
    to scroll past.
    """
    bids_dir = Path(bids_dir)
    links: Counter = Counter()
    n_series = n_dropped = 0

    for subject, session in list_units(bids_dir):
        try:
            table = build_decision_table(bids_dir, subject, session)
        except DecisionTableError:
            continue
        for s in table.series:
            n_series += 1
            protocol = s.protocol or s.description or "(unnamed)"
            if s.dropped:
                n_dropped += 1
                links[(protocol, "— dropped —")] += 1
                continue
            for path in s.outputs:
                key = bids_key(path)
                datatype, suffix = key.split("/", 1)
                links[(protocol, datatype)] += 1
                links[(datatype, suffix)] += 1

    return {
        "bids_dir": str(bids_dir),
        "n_series": n_series,
        "n_dropped": n_dropped,
        "links": [
            {"source": a, "target": b, "value": v}
            for (a, b), v in sorted(links.items(), key=lambda kv: -kv[1])
        ],
    }
