"""Pair BOLD runs with the physio recording and block that covers each of them.

fmriprep hands over every preprocessed BOLD of a subject as one list; a
BIOPAC recording covers a session, one block per run **in scan order**. So a
run's block is its position, by acquisition time, among the runs the same
recording covers.

* One recording → it covers every run: run *i* (in scan order) is block *i*.
* Several recordings → each covers one session. ``sessions`` names which
  (one label per recording, in order); without it they are matched to the
  runs' ``ses-`` labels when the file names carry one, else by sorted order.
  Runs from sessions with no recording are skipped, not corrected.
* ``blocks`` given explicitly → used as-is, one index per paired run, for
  recordings with extra blocks (an aborted run, a localizer with triggers).

``order_key`` gives the scan order (the sidecar's AcquisitionTime); without
one, or when a run has no key, the runs keep the order they came in, which
is file-name order and only right by luck.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_SES = re.compile(r"(?:^|[_/])ses-([A-Za-z0-9]+)")


@dataclass(frozen=True)
class Pairing:
    bold: str
    physio_file: str
    block: int
    session: str | None
    order: str            # "acquisition_time" | "given"


def session_of(name: str) -> str | None:
    m = _SES.search(Path(name).name)
    return m.group(1) if m else None


def pair_runs(
    bolds: list[str],
    physio_files: list[str],
    blocks: list[int] | None = None,
    *,
    sessions: list[str] | None = None,
    order_key: Callable[[str], float | None] | None = None,
) -> tuple[list[Pairing], list[str]]:
    """``(pairings, skipped)``: one :class:`Pairing` per covered BOLD, in the
    order the runs were given, plus the runs no recording covers.

    ``ValueError`` when the recordings cannot be matched to the runs'
    sessions, or ``blocks`` has the wrong length.
    """
    bolds = [str(b) for b in bolds]
    physio_files = [str(p) for p in physio_files]
    if not bolds:
        return [], []
    if not physio_files:
        raise ValueError("no physio recording given")
    if sessions is not None and len(sessions) != len(physio_files):
        raise ValueError(f"'sessions' names {len(sessions)} session(s) for {len(physio_files)} recording(s); give one per recording")

    by_ses: dict[str | None, list[str]] = {}
    for b in bolds:
        by_ses.setdefault(session_of(b), []).append(b)
    run_sessions = list(by_ses)

    # recording -> (session label, its runs)
    if sessions is not None:
        labels = [str(s) for s in sessions]
        missing = [s for s in labels if s not in by_ses]
        if missing:
            raise ValueError(
                f"no BOLD runs for session(s) {missing}; the runs are in session(s) "
                f"{[s for s in run_sessions]}"
            )
        groups = [(s, p, by_ses[s]) for s, p in zip(labels, physio_files)]
    elif len(physio_files) == 1:
        groups = [(None, physio_files[0], bolds)]
    else:
        if len(run_sessions) != len(physio_files):
            raise ValueError(
                f"{len(physio_files)} physio recording(s) for {len(run_sessions)} session(s) "
                f"({', '.join(str(s) for s in run_sessions)}); set 'sessions' to say which session each recording covers"
            )
        acq_ses = [session_of(p) for p in physio_files]
        if all(acq_ses) and None not in run_sessions and set(acq_ses) == set(run_sessions):
            files_for = dict(zip(acq_ses, physio_files))
            groups = [(s, files_for[s], by_ses[s]) for s in run_sessions]
        else:
            groups = [(s, p, by_ses[s]) for s, p in zip(run_sessions, sorted(physio_files))]

    covered = {b for _, _, runs in groups for b in runs}
    skipped = [b for b in bolds if b not in covered]

    paired: dict[str, Pairing] = {}
    for ses, physio, runs in groups:
        keys = [order_key(b) if order_key else None for b in runs]
        if all(k is not None for k in keys):
            ordered = [b for _, b in sorted(zip(keys, runs), key=lambda kb: kb[0])]
            order = "acquisition_time"
        else:
            ordered, order = list(runs), "given"
        for i, b in enumerate(ordered):
            paired[b] = Pairing(bold=b, physio_file=physio, block=i, session=ses, order=order)
    out = [paired[b] for b in bolds if b in paired]

    if blocks is not None:
        if len(blocks) != len(out):
            raise ValueError(f"'blocks' lists {len(blocks)} block index(es) for {len(out)} paired BOLD run(s); give one per run")
        out = [Pairing(bold=p.bold, physio_file=p.physio_file, block=int(k), session=p.session, order="explicit")
               for p, k in zip(out, blocks)]
    return out, skipped
