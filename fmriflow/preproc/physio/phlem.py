"""PhLEM physiological model: from raw pulse-ox / respiration traces to per-TR regressors.

A port of the lab's Python translation of the PhLEM MATLAB toolbox
(Verstynen & Deshpande 2011). The pipeline per channel is:

1. transform (``abs`` + zero-mean for PPG, zero-mean for RESP),
2. first-order Butterworth band-pass,
3. two-pass peak detection (Billauer's ``peakdet``) → one event per beat /
   breath, with a refractory ``rate`` so no two events sit closer than that,
4. regressors:
   * **RETROICOR** — sine/cosine of the cardiac / respiratory phase
     (phase expansions 1,2 for PPG; 1 for RESP), sampled at TR onsets,
   * **Rate** — events per TR,
   * **RVHR** — respiration-volume-per-time and heart-rate variation
     (Chang et al.), z-scored and convolved with the RRF / CRF.

Numerical choices are kept exactly as in the source, including the
band-pass ``Wn`` values, which are ``f / Hz`` rather than SciPy's
``f / (Hz / 2)`` — halving the nominal pass-band. Changing that would
change every regressor, so it stays; see the note at :data:`PREPROC_OPTIONS`.

Only the ``np.cast`` calls (removed in NumPy 2) and two ``np.empty``
shape bugs in the unused branches were fixed.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

CHANNELS = ("PPG", "RESP")
MODEL_TERMS = ("RETROICOR", "Rate", "RVHR")


def _nanmean(x):
    x = np.asarray(x, dtype=float)
    return float(np.sum(x[~np.isnan(x)]) / np.sum(~np.isnan(x)))


def _nanstd(x):
    x = np.asarray(x, dtype=float)
    return float(np.sqrt(np.nansum((x - _nanmean(x)) ** 2) / (np.sum(~np.isnan(x)) - 1)))


def preproc_options(channel: str, hz: float) -> dict[str, Any]:
    """Filtering / peak-finding options per channel (PhLEM defaults).

    ``Wn`` is normalised as ``f / Hz`` (the original code's convention), so
    PPG's nominal 1–6 Hz band is really 0.5–3 Hz and RESP's 0.25–0.5 Hz
    band is 0.125–0.25 Hz, at SciPy's Nyquist normalisation.
    """
    if channel == "PPG":
        return dict(
            rate=hz / 2,               # refractory period for peaks (samples)
            peak_rise=0.1,
            filter="butter",
            phase_expand=[1, 2],
            Wn=np.array([1, 6]) / hz,
            Hz=hz,
            transform="abs",
        )
    if channel == "RESP":
        return dict(
            rate=hz * 1.5,
            peak_rise=0.2,
            filter="butter",
            phase_expand=[1],
            Wn=np.array([1 / 4, 1 / 2]) / hz,
            Hz=hz,
            transform="none",
        )
    raise ValueError(f"unknown channel {channel!r}; expected one of {CHANNELS}")


PREPROC_OPTIONS = preproc_options


def peakdet(v, delta: float):
    """Local maxima / minima of ``v`` (Billauer 2005, public domain).

    A point is a maximum if it is the largest seen and is later followed
    by a value at least ``delta`` lower. Returns ``(maxtab, mintab)``, each
    ``(n, 2)`` of ``[index, value]``.
    """
    v = np.asarray(v, dtype=float).ravel()
    if not np.isscalar(delta):
        raise ValueError("delta must be a scalar")
    if delta <= 0:
        raise ValueError("delta must be positive")
    maxtab: list[list[float]] = []
    mintab: list[list[float]] = []
    mn, mx = np.inf, -np.inf
    mnpos = mxpos = np.nan
    lookformax = True
    for i, this in enumerate(v):
        if this > mx:
            mx, mxpos = this, i
        if this < mn:
            mn, mnpos = this, i
        if lookformax:
            if this < mx - delta:
                maxtab.append([mxpos, mx])
                mn, mnpos = this, i
                lookformax = False
        else:
            if this > mn + delta:
                mintab.append([mnpos, mn])
                mx, mxpos = this, i
                lookformax = True
    return np.array(maxtab).reshape(-1, 2), np.array(mintab).reshape(-1, 2)


class PhLEMData:
    """Physio traces for one run plus the model built on them.

    ``data`` maps ``"PPG"`` / ``"RESP"`` to ``{"data": trace, "hz": rate}``;
    ``time`` is the sample-time vector (seconds) and ``tr`` the TR in seconds.
    """

    def __init__(self, data: dict[str, dict[str, Any]], time, tr: float) -> None:
        self.TR = float(tr)
        self.time = np.asarray(time, dtype=float)
        self.channels: dict[str, dict[str, Any]] = {}
        for k, v in data.items():
            if k not in CHANNELS:
                raise ValueError(f"unknown data type {k!r}; must be one of {CHANNELS}")
            self.channels[k] = {
                "data": np.asarray(v["data"], dtype=float),
                "hz": float(v["hz"]),
                "preprocOpt": preproc_options(k, float(v["hz"])),
            }

    def __contains__(self, channel: str) -> bool:
        return channel in self.channels

    def __getitem__(self, channel: str) -> dict[str, Any]:
        return self.channels[channel]

    # ── preprocessing ───────────────────────────────────────────────

    def preprocess(self, channel: str = "all", **opts: Any) -> None:
        """Transform, filter and find events for one channel (or all)."""
        if channel == "all":
            for c in CHANNELS:
                if c in self.channels:
                    self.preprocess(c)
            return
        d = self.channels[channel]
        d["preprocOpt"].update(opts)
        opt = d["preprocOpt"]

        if opt["transform"] == "abs":
            x = np.abs(d["data"])
            x = x - _nanmean(x)
        elif opt["transform"] in ("z", "z-score", "zscore"):
            x = (d["data"] - _nanmean(d["data"])) / _nanstd(d["data"])
        else:
            x = d["data"] - _nanmean(d["data"])

        if opt["filter"] == "butter":
            from scipy.signal import butter, lfilter
            if np.any(opt["Wn"]):
                b, a = butter(1, opt["Wn"], "band")
                x = lfilter(b, a, x)
        elif opt["filter"] == "gaussian":
            from scipy import stats
            sigma = opt["Wn"]
            n = int(np.round(sigma * 5) * 2)
            t = np.arange(1, n)
            v = stats.norm.pdf(t, (n + 1) / 2, sigma)
            pb = np.ones(len(v) - 1) * x[0]
            pe = np.ones(len(v) - 1) * x[-1]
            x = np.hstack((pb, x, pe))
            x = np.convolve(x, v)
            cut = int(np.round(1.5 * n))
            x = x[cut - 1:-cut + 1]
        else:
            raise ValueError(f"unknown filter type {opt['filter']!r}")
        d["smoothed_data"] = x

        # First pass finds every wiggle; the threshold for the second pass is
        # a fraction of the 20th-highest peak, which ignores a few outliers.
        maxtab, _ = peakdet(x, 1e-14)
        if maxtab.shape[0] < 2:
            raise ValueError(f"{channel}: could not find peaks (trace flat or too short)")
        sorted_peaks = np.sort(maxtab[:, 1])
        peak_resp = sorted_peaks[-20] if len(sorted_peaks) > 20 else sorted_peaks[1]
        maxtab, _ = peakdet(x, opt["peak_rise"] * peak_resp)
        events = np.zeros(d["data"].shape)
        peaks = maxtab[:, 0]
        keep = np.nonzero(np.diff(peaks) > opt["rate"])[0]
        # The original starts at the second peak; kept for identical output.
        new_peaks = np.round(peaks[np.hstack(([1], keep + 1))]).astype("uint32")
        if len(new_peaks) < 5:
            raise ValueError(f"{channel}: could not find peaks (fewer than 5 events)")
        events[new_peaks] = 1
        d["events"] = events

    # ── model ───────────────────────────────────────────────────────

    def make_model(self, terms: tuple[str, ...] | list[str] | None = None) -> tuple[np.ndarray, list[str]]:
        """Regressor matrix ``(n_trs, n_regressors)`` and column names.

        ``terms`` picks from :data:`MODEL_TERMS`; ``None`` builds the full
        model (RETROICOR, Rate, RVHR on every channel present).
        """
        terms = tuple(terms) if terms else MODEL_TERMS
        parts: list[np.ndarray] = []
        labels: list[str] = []
        for term in terms:
            fn = _TERMS.get(term)
            if fn is None:
                raise ValueError(f"unknown model term {term!r}; expected one of {MODEL_TERMS}")
            x, lab = fn(self)
            parts.append(x)
            labels += lab
        n = min(p.shape[0] for p in parts)
        # Rate/RVHR count TRs slightly differently at the tail; align on the shortest.
        X = np.hstack([p[:n] for p in parts])
        return X, labels

    # Backwards-compatible aliases (names from the original class).
    makeModel = make_model


def _tr_indices(ph: PhLEMData) -> np.ndarray:
    tr_timestamps = np.arange(0, ph.time[-1], ph.TR) / np.mean(np.diff(ph.time))
    return np.round(tr_timestamps).astype("uint32")


def retroicor(ph: PhLEMData, channels: tuple[str, ...] = CHANNELS,
              phase_expand: tuple[tuple[int, ...], ...] | None = None) -> tuple[np.ndarray, list[str]]:
    """Sine/cosine of the unwrapped cardiac / respiratory phase at each TR."""
    import scipy.interpolate as interp

    channels = tuple(c for c in channels if c in ph)
    if phase_expand is None:
        phase_expand = tuple(tuple(ph[c]["preprocOpt"]["phase_expand"]) for c in channels)
    t_idx = _tr_indices(ph)
    n_trs = len(t_idx)
    rows: list[np.ndarray] = []
    labels: list[str] = []
    for c, expand in zip(channels, phase_expand):
        d = ph[c]
        events = np.nonzero(d["events"])[0]
        uwp_phase = 2 * np.pi * np.arange(len(events))
        spl = interp.UnivariateSpline(ph.time[events], uwp_phase, k=3, s=0.001)
        tmp_phase = spl(ph.time)
        for p in (expand or (1,)):
            phase = tmp_phase * p
            intp = interp.interp1d(ph.time, phase, kind="linear", bounds_error=False)
            phase_tr = intp(ph.time[t_idx])
            rows.append(np.sin(phase_tr)); labels.append(f"RETROICOR_{c}_phase{p}_sin")
            rows.append(np.cos(phase_tr)); labels.append(f"RETROICOR_{c}_phase{p}_cos")
    X = np.vstack(rows).T if rows else np.empty((n_trs, 0))
    return X, labels


def rate(ph: PhLEMData, channels: tuple[str, ...] = CHANNELS) -> tuple[np.ndarray, list[str]]:
    """Events (beats / breaths) per TR."""
    t_idx = _tr_indices(ph)
    edges = np.hstack((t_idx, len(ph.time)))
    n_trs = len(t_idx)
    rows: list[np.ndarray] = []
    labels: list[str] = []
    for c in channels:
        if c not in ph:
            continue
        ee = np.nonzero(ph[c]["events"])[0]
        counts, _ = np.histogram(ee, edges)
        rows.append(counts.astype(float)); labels.append(f"Rate_{c}")
    X = np.vstack(rows).T if rows else np.empty((n_trs, 0))
    return X, labels


def rvhr(ph: PhLEMData, channels: tuple[str, ...] = CHANNELS) -> tuple[np.ndarray, list[str]]:
    """Respiration-volume and heart-rate variation (Chang et al.), RRF/CRF-convolved."""
    tr = ph.TR
    n_trs = int(np.ceil(ph.time[-1] / tr))
    cols: list[np.ndarray] = []
    labels: list[str] = []

    if "RESP" in ph and "RESP" in channels:
        d = ph["RESP"]
        tr_vec = np.floor(ph.time / tr).astype("uint32")
        rv = np.empty(n_trs)
        for i in range(n_trs):
            idx = np.any(np.array([tr_vec == i - 1, tr_vec == i, tr_vec == i + 1]), axis=0)
            rv[i] = _nanstd(d["smoothed_data"][idx])
        rv = (rv - _nanmean(rv)) / _nanstd(rv)
        t = np.arange(0, 28, tr)
        rrf = 0.6 * t ** 2.1 * np.exp(-t / 1.6) - 0.0023 * t ** 3.54 * np.exp(-t / 4.25)
        cols.append(np.convolve(rv, rrf)[:n_trs]); labels.append("RespiratoryVariation")

    if "PPG" in ph and "PPG" in channels:
        d = ph["PPG"]
        beats = ph.time[d["events"] == 1]
        tr_vec = np.floor(beats / tr)
        hr = np.zeros(n_trs)
        for i in range(n_trs):
            idx = np.any(np.array([tr_vec == i - 1, tr_vec == i, tr_vec == i + 1]), axis=0)
            if len(beats[idx]) > 1:
                hr[i] = 60 / np.diff(beats[idx]).mean()
        hr = (hr - _nanmean(hr)) / _nanstd(hr)
        t = np.arange(0, 28, tr)
        crf = 0.6 * t ** 2.7 * np.exp(-t / 1.6) - 16 / np.sqrt(2 * np.pi * 9) * np.exp(-0.5 * (t - 12) ** 2 / 9)
        cols.append(np.convolve(hr, crf)[:n_trs]); labels.append("HeartRateVariation")

    X = np.vstack(cols).T if cols else np.empty((n_trs, 0))
    return X, labels


_TERMS: dict[str, Callable[[PhLEMData], tuple[np.ndarray, list[str]]]] = {
    "RETROICOR": retroicor, "Rate": rate, "RVHR": rvhr,
}


def build_regressors(
    cardiac, respiratory, time, tr: float, sampling_rate: float, *,
    terms: tuple[str, ...] | list[str] | None = None,
    ppg_peak_rise: float | None = None, resp_peak_rise: float | None = None,
) -> tuple[np.ndarray, list[str]]:
    """One call from raw traces to the regressor matrix and its column names."""
    ph = PhLEMData(
        {"PPG": {"data": cardiac, "hz": sampling_rate}, "RESP": {"data": respiratory, "hz": sampling_rate}},
        time, tr,
    )
    ph.preprocess("PPG", **({"peak_rise": ppg_peak_rise} if ppg_peak_rise is not None else {}))
    ph.preprocess("RESP", **({"peak_rise": resp_peak_rise} if resp_peak_rise is not None else {}))
    return ph.make_model(terms)
