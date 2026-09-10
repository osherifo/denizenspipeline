"""Split a BIOPAC ``.acq`` recording into scan blocks.

The scanner emits one TTL pulse per TR on a trigger channel. A long gap
between pulses separates two runs, so the recording splits into blocks
at those gaps. Each block carries time, trigger, cardiac (PPG) and
respiratory traces trimmed to ``[first pulse, last pulse + one TR]``.

Reading the file needs ``bioread`` (imported lazily so the rest of the
package works without it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Default channel layout of the acquisition file (pulse-ox, unused, respiration, trigger).
DEFAULT_PPG_CHANNEL = 0
DEFAULT_RESP_CHANNEL = 2
DEFAULT_TTL_CHANNEL = 3
DEFAULT_RUN_GAP_S = 10.0
DEFAULT_TTL_THRESHOLD = -1.1

DATA_NAMES = ("time", "trigger", "cardiac", "respiratory")
UNITS = ("s", "V", "V", "V")


@dataclass
class PhysioBlock:
    """One run's worth of physio: ``data`` is ``(4, n_samples)`` in :data:`DATA_NAMES` order."""

    index: int
    data: Any                          # np.ndarray (4, n_samples)
    sampling_rate: float
    tr_samples: int                    # median samples between TTL pulses
    n_pulses: int

    @property
    def duration_s(self) -> float:
        return float(self.data.shape[1] / self.sampling_rate)

    @property
    def tr_s(self) -> float:
        return float(self.tr_samples / self.sampling_rate)

    def summary(self) -> dict[str, Any]:
        return {
            "index": self.index, "duration_s": round(self.duration_s, 3),
            "n_samples": int(self.data.shape[1]), "n_pulses": self.n_pulses,
            "tr_s": round(self.tr_s, 4), "n_trs": self.n_pulses,     # one trigger per TR
        }


@dataclass
class AcqSplit:
    blocks: list[PhysioBlock]
    sampling_rate: float
    source: str
    data_names: tuple[str, ...] = DATA_NAMES
    units: tuple[str, ...] = UNITS
    channels: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "source": self.source, "sampling_rate": self.sampling_rate,
            "channels": dict(self.channels), "n_blocks": len(self.blocks),
            "blocks": [b.summary() for b in self.blocks],
        }


def split_acq(
    physio_file: str | Path,
    *,
    ppg_channel: int = DEFAULT_PPG_CHANNEL,
    resp_channel: int = DEFAULT_RESP_CHANNEL,
    ttl_channel: int = DEFAULT_TTL_CHANNEL,
    run_gap_s: float = DEFAULT_RUN_GAP_S,
    ttl_threshold: float = DEFAULT_TTL_THRESHOLD,
    min_pulses: int = 5,
) -> AcqSplit:
    """Split ``physio_file`` into blocks at gaps in the TTL train.

    A TTL pulse is a drop in the trigger channel steeper than
    ``ttl_threshold`` between consecutive samples. Gaps longer than
    ``run_gap_s`` start a new block; blocks with ``min_pulses`` or fewer
    pulses are dropped (scanner test pulses, aborted runs).
    """
    import numpy as np

    try:
        import bioread
    except ImportError as e:  # pragma: no cover - exercised by preflight, not tests
        raise ImportError("reading .acq files needs the 'bioread' package (pip install bioread)") from e

    path = Path(physio_file)
    if not path.is_file():
        raise FileNotFoundError(f"physio file not found: {path}")
    rec = bioread.read_file(str(path))
    n_ch = len(rec.channels)
    for label, ch in (("ppg", ppg_channel), ("resp", resp_channel), ("ttl", ttl_channel)):
        if not 0 <= ch < n_ch:
            raise ValueError(f"{label}_channel={ch} but {path.name} has {n_ch} channel(s)")

    hz = float(rec.channels[ttl_channel].samples_per_second)
    ttl_raw = np.asarray(rec.channels[ttl_channel].data[:], dtype=float)
    ppg_raw = np.asarray(rec.channels[ppg_channel].data[:], dtype=float)
    resp_raw = np.asarray(rec.channels[resp_channel].data[:], dtype=float)

    # Falling edges of the trigger; the last three samples are ignored as in the original.
    pulses = np.nonzero(np.diff(ttl_raw)[:-3] < ttl_threshold)[0] + 1
    if pulses.size == 0:
        raise ValueError(f"no TTL pulses found on channel {ttl_channel} of {path.name} (threshold {ttl_threshold})")
    gaps = np.diff(pulses)
    starts = np.nonzero(gaps > run_gap_s * hz)[0] + 1
    bounds = np.hstack([0, starts, pulses.size])

    blocks: list[PhysioBlock] = []
    for s, e in zip(bounds[:-1], bounds[1:]):
        if e - s <= min_pulses:
            continue
        p = pulses[s:e]
        tr_samples = int(np.median(np.diff(p)))
        lo, hi = int(p[0]), int(p[-1] + tr_samples)
        d_ppg, d_resp, d_trig = ppg_raw[lo:hi], resp_raw[lo:hi], ttl_raw[lo:hi]
        n = min(len(d_ppg), len(d_resp), len(d_trig))
        d_ppg, d_resp, d_trig = d_ppg[:n], d_resp[:n], d_trig[:n]
        t = np.arange(n) / hz
        blocks.append(PhysioBlock(
            index=len(blocks), data=np.vstack([t, d_trig, d_ppg, d_resp]),
            sampling_rate=hz, tr_samples=tr_samples, n_pulses=int(p.size),
        ))
    return AcqSplit(
        blocks=blocks, sampling_rate=hz, source=str(path),
        channels={"ppg": ppg_channel, "resp": resp_channel, "ttl": ttl_channel},
    )
