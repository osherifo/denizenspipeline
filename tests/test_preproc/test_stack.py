"""Phase 1 — config + manifest shape tests for the unified preproc stack.

Covers:
- PreprocStack / BootstrapStage / TransformStage / StepRecord JSON round-trip.
- Legacy PreprocConfig auto-wraps cleanly into a single-bootstrap stack.
- Legacy manifests with ``additional_steps: list[str]`` load unchanged,
  with each string converted into a minimal StepRecord(name=str).
- New manifests with ``additional_steps: list[StepRecord]`` round-trip
  preserving all fields.

These tests are the load-bearing back-compat guarantees for the
preprocessing-stack rollout — if any of these regress, existing
on-disk manifests stop loading.
"""

from __future__ import annotations

import json

from fmriflow.preproc.manifest import (
    PreprocConfig,
    PreprocManifest,
    RunRecord,
)
from fmriflow.preproc.stack import (
    BootstrapStage,
    PreprocStack,
    StepRecord,
    TransformStage,
)


# ── PreprocStack ────────────────────────────────────────────────────────


class TestPreprocStack:
    def test_minimal_construction(self):
        stack = PreprocStack(bootstrap=BootstrapStage(kind="fmriprep"))
        assert stack.bootstrap.kind == "fmriprep"
        assert stack.bootstrap.workflow is None
        assert stack.bootstrap.params == {}
        assert stack.transforms == []

    def test_json_round_trip_full_stack(self, tmp_path):
        stack = PreprocStack(
            bootstrap=BootstrapStage(
                kind="nipype",
                workflow="reference",
                params={"output_space": "MNI152NLin2009cAsym", "with_freesurfer": False},
            ),
            transforms=[
                TransformStage(name="smooth", params={"fwhm": 6}),
                TransformStage(
                    name="regress_confounds",
                    params={"strategy": "motion_24", "high_pass": 0.01},
                ),
            ],
        )

        path = tmp_path / "stack.json"
        stack.save(path)
        reloaded = PreprocStack.from_json(path)

        assert reloaded == stack
        assert reloaded.bootstrap.workflow == "reference"
        assert len(reloaded.transforms) == 2
        assert reloaded.transforms[1].params["high_pass"] == 0.01

    def test_from_dict_tolerates_missing_transforms(self):
        # Older saved stacks may not have a 'transforms' key at all.
        stack = PreprocStack.from_dict({"bootstrap": {"kind": "fmriprep"}})
        assert stack.transforms == []

    def test_from_dict_tolerates_null_transforms(self):
        stack = PreprocStack.from_dict(
            {"bootstrap": {"kind": "fmriprep"}, "transforms": None}
        )
        assert stack.transforms == []


# ── PreprocStack.from_legacy ────────────────────────────────────────────


class TestFromLegacy:
    def test_wraps_single_backend_config(self):
        config = PreprocConfig(
            subject="sub01",
            backend="fmriprep",
            output_dir="/tmp/out",
            bids_dir="/tmp/bids",
            backend_params={"output_spaces": "MNI152NLin2009cAsym", "nthreads": 8},
        )
        stack = PreprocStack.from_legacy(config)

        assert stack.bootstrap.kind == "fmriprep"
        assert stack.bootstrap.params == {
            "output_spaces": "MNI152NLin2009cAsym",
            "nthreads": 8,
        }
        assert stack.transforms == []

    def test_drops_subject_and_paths(self):
        # The stack is a recipe — subject/paths belong to the run layer.
        config = PreprocConfig(
            subject="sub01",
            backend="custom",
            output_dir="/tmp/out",
            bids_dir="/tmp/bids",
        )
        stack = PreprocStack.from_legacy(config)
        for value in (stack.bootstrap.params.values() if stack.bootstrap.params else ()):
            assert "sub01" not in str(value)
            assert "/tmp/out" not in str(value)


# ── StepRecord ──────────────────────────────────────────────────────────


class TestStepRecord:
    def test_legacy_string_wrap(self):
        s = StepRecord.from_legacy_string("smoothing_5mm")
        assert s.name == "smoothing_5mm"
        assert s.version == ""
        assert s.params == {}
        assert s.input_stage == 0

    def test_from_dict_full(self):
        s = StepRecord.from_dict({
            "name": "smooth",
            "version": "0.3",
            "params": {"fwhm": 6},
            "input_stage": 1,
            "output_dir": "/tmp/smooth_out",
            "duration_s": 12.4,
            "fingerprint": "abc123",
        })
        assert s.name == "smooth"
        assert s.params == {"fwhm": 6}
        assert s.duration_s == 12.4
        assert s.fingerprint == "abc123"


# ── PreprocManifest back-compat ────────────────────────────────────────


def _minimal_manifest_dict(extra: dict | None = None) -> dict:
    base = {
        "subject": "sub01",
        "dataset": "study1",
        "sessions": [],
        "runs": [],
        "backend": "fmriprep",
        "backend_version": "23.2.1",
        "parameters": {},
        "space": "MNI152NLin2009cAsym",
    }
    if extra:
        base.update(extra)
    return base


class TestManifestLegacySteps:
    def test_legacy_list_of_strings_loads(self):
        # The shape every existing on-disk manifest uses today.
        data = _minimal_manifest_dict({
            "additional_steps": ["smoothing_5mm", "bandpass_0.01_0.1"],
        })
        manifest = PreprocManifest.from_dict(data)

        assert len(manifest.additional_steps) == 2
        assert all(isinstance(s, StepRecord) for s in manifest.additional_steps)
        assert manifest.additional_steps[0].name == "smoothing_5mm"
        assert manifest.additional_steps[1].name == "bandpass_0.01_0.1"
        # Wrapped entries default the rest of the fields cleanly.
        assert manifest.additional_steps[0].params == {}
        assert manifest.additional_steps[0].version == ""

    def test_empty_steps_loads(self):
        data = _minimal_manifest_dict({"additional_steps": []})
        manifest = PreprocManifest.from_dict(data)
        assert manifest.additional_steps == []

    def test_missing_steps_field_loads(self):
        # Field absent → default factory → empty list.
        data = _minimal_manifest_dict()
        manifest = PreprocManifest.from_dict(data)
        assert manifest.additional_steps == []

    def test_invalid_entry_type_raises(self):
        data = _minimal_manifest_dict({"additional_steps": [123]})
        try:
            PreprocManifest.from_dict(data)
        except TypeError as e:
            assert "additional_steps" in str(e)
        else:
            assert False, "expected TypeError for non-str/dict/StepRecord entry"


class TestManifestNewSteps:
    def test_new_dict_entries_round_trip(self, tmp_path):
        manifest = PreprocManifest(
            subject="sub01",
            dataset="study1",
            sessions=["ses01"],
            runs=[
                RunRecord(
                    run_name="run01",
                    source_file="sub-01_run-01_bold.nii.gz",
                    output_file="sub-01_run-01_desc-preproc_bold.nii.gz",
                    n_trs=200,
                    shape=[64, 64, 30, 200],
                ),
            ],
            backend="nipype",
            backend_version="0.1.0",
            parameters={"workflow": "reference"},
            space="MNI152NLin2009cAsym",
            additional_steps=[
                StepRecord(
                    name="smooth",
                    version="0.3",
                    params={"fwhm": 6},
                    input_stage=0,
                    output_dir="/tmp/smooth_out",
                    duration_s=12.4,
                    fingerprint="abc123",
                ),
                StepRecord(
                    name="regress_confounds",
                    params={"strategy": "motion_24"},
                    input_stage=1,
                ),
            ],
        )

        path = tmp_path / "manifest.json"
        manifest.save(path)
        reloaded = PreprocManifest.from_json(path)

        assert len(reloaded.additional_steps) == 2
        assert reloaded.additional_steps[0].name == "smooth"
        assert reloaded.additional_steps[0].params == {"fwhm": 6}
        assert reloaded.additional_steps[0].duration_s == 12.4
        assert reloaded.additional_steps[0].fingerprint == "abc123"
        assert reloaded.additional_steps[1].input_stage == 1

    def test_serialized_form_is_plain_json(self, tmp_path):
        # The on-disk file should be plain JSON dicts, not pickled
        # dataclasses — so other tools can read it.
        manifest = PreprocManifest(
            subject="sub01",
            dataset="study1",
            sessions=[],
            runs=[],
            backend="nipype",
            backend_version="0.1.0",
            parameters={},
            space="T1w",
            additional_steps=[StepRecord(name="smooth", params={"fwhm": 6})],
        )
        path = tmp_path / "manifest.json"
        manifest.save(path)

        raw = json.loads(path.read_text())
        assert isinstance(raw["additional_steps"], list)
        assert isinstance(raw["additional_steps"][0], dict)
        assert raw["additional_steps"][0]["name"] == "smooth"
        assert raw["additional_steps"][0]["params"] == {"fwhm": 6}
