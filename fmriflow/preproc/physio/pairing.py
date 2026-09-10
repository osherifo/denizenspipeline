"""Pair BOLD runs with the physio recording and block that covers each of them.

fmriprep hands over every preprocessed BOLD of a subject as one sorted list;
a BIOPAC recording covers a session, one block per run in scan order. So a
run's block is its position among the runs the same recording covers.

* One recording → it covers every run: run *i* is block *i*.
* Several recordings → each covers one session. They are matched to the
  runs' ``ses-`` labels when their file names carry one, else by order.
  Within a session, run *i* is block *i*.
* ``blocks`` given explicitly → used as-is, one index per run, for
  recordings with extra blocks (an aborted run, a localizer with triggers).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SES = re.compile(r"(?:^|[_/])ses-([A-Za-z0-9]+)")


@dataclass(frozen=True)
class Pairing:
    bold: str
    physio_file: str
    block: int
    session: str | None


def session_of(name: str) -> str | None:
    m = _SES.search(Path(name).name)
    return m.group(1) if m else None


def pair_runs(bolds: list[str], physio_files: list[str], blocks: list[int] | None = None) -> list[Pairing]:
    """One :class:`Pairing` per BOLD, in the order given.

    ``ValueError`` when the recordings cannot be matched to the runs'
    sessions, or ``blocks`` has the wrong length.
    """
    bolds = [str(b) for b in bolds]
    physio_files = [str(p) for p in physio_files]
    if not bolds:
        return []
    if not physio_files:
        raise ValueError("no physio recording given")
    if blocks is not None and len(blocks) != len(bolds):
        raise ValueError(f"'blocks' lists {len(blocks)} block index(es) for {len(bolds)} BOLD run(s); give one per run")

    if len(physio_files) == 1:
        groups: list[tuple[str | None, str, list[str]]] = [(None, physio_files[0], bolds)]
    else:
        # Runs grouped by session, in order of first appearance.
        by_ses: dict[str | None, list[str]] = {}
        for b in bolds:
            by_ses.setdefault(session_of(b), []).append(b)
        sessions = list(by_ses)
        if len(sessions) != len(physio_files):
            raise ValueError(
                f"{len(physio_files)} physio recording(s) for {len(sessions)} session(s) "
                f"({', '.join(str(s) for s in sessions)}); give one recording per session or a single recording for all runs"
            )
        acq_ses = [session_of(p) for p in physio_files]
        if all(acq_ses) and None not in sessions and set(acq_ses) == set(sessions):
            files_for = dict(zip(acq_ses, physio_files))
            groups = [(s, files_for[s], by_ses[s]) for s in sessions]
        else:
            groups = [(s, p, by_ses[s]) for s, p in zip(sessions, sorted(physio_files))]

    out: list[Pairing] = []
    for ses, physio, runs in groups:
        for i, b in enumerate(runs):
            out.append(Pairing(bold=b, physio_file=physio, block=i, session=ses))
    if blocks is not None:
        by_bold = {p.bold: p for p in out}
        out = [Pairing(bold=b, physio_file=by_bold[b].physio_file, block=int(k), session=by_bold[b].session)
               for b, k in zip(bolds, blocks)]
    return out
