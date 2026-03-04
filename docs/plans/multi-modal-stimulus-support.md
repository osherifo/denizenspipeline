# Plan: Multi-Modal Stimulus Support

## Context

`StimRun` is hardcoded to language stimuli — it has `textgrid` and `trfile` fields, and all 11 feature extractors access them directly. This blocks support for audio stimuli (spectral features for auditory encoding models) and visual stimuli (motion/luminance features for visual encoding models). The goal is to introduce typed stimulus containers, new loaders, and new extractors while keeping all existing code working unchanged.

## Design

### Typed Stimulus Containers

Three frozen dataclasses in `core/types.py`:

```python
@dataclass(frozen=True)
class LanguageStim:
    textgrid: Any
    trfile: Any

@dataclass(frozen=True)
class AudioStim:
    waveform: np.ndarray   # (n_samples,)
    sample_rate: int
    tr_times: np.ndarray   # TR onset times in seconds

@dataclass(frozen=True)
class VisualStim:
    video_path: Path       # path to video file (frames loaded on demand)
    fps: float
    n_frames: int
    tr_times: np.ndarray   # TR onset times in seconds
```

### Refactored StimRun

`StimRun` gets a `stimulus` field. `textgrid`/`trfile` become backward-compatible properties:

```python
@dataclass(frozen=True)
class StimRun:
    name: str
    stimulus: LanguageStim | AudioStim | VisualStim
    language: str = "en"
    modality: str = "reading"

    @property
    def textgrid(self):
        return self.stimulus.textgrid if isinstance(self.stimulus, LanguageStim) else None

    @property
    def trfile(self):
        return self.stimulus.trfile if isinstance(self.stimulus, LanguageStim) else None
```

All 11 existing extractors do `stim_run.textgrid` / `stim_run.trfile` — these keep working via properties, zero changes needed.

### TR Alignment Utility

New `core/alignment.py` with `align_to_trs(features, feature_times, tr_times)` — bins high-rate features into TR windows using `np.searchsorted`. Used by all audio/visual extractors.

### New Stimulus Loaders

| Loader | Config | Creates |
|--------|--------|---------|
| `audio` | `stimulus.path` (dir of .wav files) + `tr`/`n_trs` | `AudioStim` per run |
| `video` | `stimulus.path` (dir of .mp4/.avi files) + `tr`/`n_trs` | `VisualStim` per run |

Both use lazy imports (`librosa` / `cv2`) with clear error messages pointing to optional dependency groups.

### New Feature Extractors

| Extractor | Input | Output | Dependency |
|-----------|-------|--------|------------|
| `mel_spectrogram` | `AudioStim` | (n_trs, n_mels) | librosa |
| `rms_energy` | `AudioStim` | (n_trs, 1) | librosa |
| `luminance` | `VisualStim` | (n_trs, 1) | opencv |
| `motion_energy` | `VisualStim` | (n_trs, 1) | opencv |

Each extractor checks `isinstance(stim_run.stimulus, AudioStim/VisualStim)` and raises `TypeError` with a clear message if wrong type.

## Implementation Steps

### 1. `core/types.py` — add stimulus containers, refactor StimRun

- Add `LanguageStim`, `AudioStim`, `VisualStim` frozen dataclasses above `StimRun`
- Replace `StimRun` fields (`textgrid`, `trfile`) with `stimulus: LanguageStim | AudioStim | VisualStim`
- Add `textgrid`/`trfile` backward-compat `@property` methods

### 2. `core/alignment.py` — new TR alignment utility

- `align_to_trs(features, feature_times, tr_times, method="mean")` → `(n_trs, n_features)`
- `searchsorted`-based binning with mean or sum aggregation

### 3. `plugins/stimulus_loaders/textgrid.py` — wrap in LanguageStim

- Change `StimRun(name=..., textgrid=..., trfile=...)` → `StimRun(name=..., stimulus=LanguageStim(textgrid=..., trfile=...))`
- Import `LanguageStim`

### 4. `plugins/stimulus_loaders/audio.py` — new AudioStimulusLoader

- `@stimulus_loader("audio")`, loads WAV files via librosa
- TR times from config `n_trs`/`tr`, or inferred from duration
- Creates `AudioStim` with waveform in memory

### 5. `plugins/stimulus_loaders/video.py` — new VideoStimulusLoader

- `@stimulus_loader("video")`, reads video metadata via cv2
- Does NOT decode frames — stores path, fps, n_frames in `VisualStim`
- TR times from config

### 6. `plugins/feature_extractors/audio.py` — mel_spectrogram + rms_energy

- `MelSpectrogramExtractor`: librosa mel spectrogram → `align_to_trs` → `(n_trs, n_mels)`
- `RMSEnergyExtractor`: librosa RMS → `align_to_trs` → `(n_trs, 1)`
- Both check `isinstance(stimulus, AudioStim)`, raise TypeError if wrong

### 7. `plugins/feature_extractors/visual.py` — luminance + motion_energy

- Shared `_read_frames_gray(video_path, n_frames)` helper using cv2
- `LuminanceExtractor`: mean frame luminance → `align_to_trs` → `(n_trs, 1)`
- `MotionEnergyExtractor`: frame-differencing → `align_to_trs` → `(n_trs, 1)`
- Both check `isinstance(stimulus, VisualStim)`, raise TypeError if wrong

### 8. `config/schema.py` — expand validation

- Add `"visual"` to modality enum
- Add validation: audio/video loaders require `stimulus.path`

### 9. `plugins/__init__.py` — register new modules

- Add imports for `stimulus_loaders.audio`, `stimulus_loaders.video`, `feature_extractors.audio`, `feature_extractors.visual`

### 10. `pyproject.toml` — optional deps + entry points

- Add `audio = ["librosa>=0.10", "soundfile>=0.12"]` and `video = ["opencv-python>=4.7"]` optional deps
- Update `all` group to include audio, video
- Add entry points for new loaders and extractors

### 11. `tests/conftest.py` — update fixtures

- Import `LanguageStim`, update `mock_stim_run` and `mock_stimuli` to use `stimulus=LanguageStim(...)` constructor

## Files Modified

- `denizenspipeline/core/types.py`
- `denizenspipeline/plugins/stimulus_loaders/textgrid.py`
- `denizenspipeline/config/schema.py`
- `denizenspipeline/plugins/__init__.py`
- `pyproject.toml`
- `tests/conftest.py`

## Files Created

- `denizenspipeline/core/alignment.py`
- `denizenspipeline/plugins/stimulus_loaders/audio.py`
- `denizenspipeline/plugins/stimulus_loaders/video.py`
- `denizenspipeline/plugins/feature_extractors/audio.py`
- `denizenspipeline/plugins/feature_extractors/visual.py`

## Verification

1. After StimRun refactor + textgrid update: all existing tests pass unchanged (backward-compat properties)
2. After alignment utility: test with synthetic data (known bins, verify correct aggregation)
3. After full implementation: `PluginRegistry.list_plugins()` shows 4 stimulus loaders, 15 feature extractors
