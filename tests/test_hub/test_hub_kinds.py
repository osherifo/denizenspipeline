"""Artifact-hub kind coverage.

A kind is only usable if it is wired into all four places at once:
``KINDS`` (validation), the install handler table, the publish lookup,
and ``PUBLISHABLE_KINDS``. Miss one and the failure is quiet — an
unknown kind reads as "nothing installed" because ``local_names`` swallows
exceptions, or publishing dies at runtime with "cannot publish kind".

``hub.schema.json`` is a fifth place, and nothing reads it at runtime, so
only a test can catch it drifting from the Python tuple.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from fmriflow.hub import installer, manifest, publisher
from fmriflow.hub.publisher import PublishError
from fmriflow.hub.service import HubService

SCHEMA_PATH = Path(manifest.__file__).parent / "hub.schema.json"

STAGE_CONFIG_KINDS = ("convert_config", "preproc_config", "autoflatten_config")


def _schema_kinds() -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text())
    return schema["$defs"]["artifact"]["properties"]["kind"]["enum"]


# ── the wiring contract ─────────────────────────────────────────────


def test_schema_enum_matches_kinds():
    """The JSON schema is documentation only — nothing else catches drift."""
    assert sorted(_schema_kinds()) == sorted(manifest.KINDS)


@pytest.mark.parametrize("kind", STAGE_CONFIG_KINDS)
def test_stage_config_kinds_are_fully_wired(kind):
    assert kind in manifest.KINDS
    assert kind in installer._HANDLERS
    assert kind in HubService.PUBLISHABLE_KINDS


def test_every_publishable_kind_can_be_installed():
    """Anything publishable must be installable, or it is a one-way trip."""
    missing = [
        k for k in HubService.PUBLISHABLE_KINDS if k not in installer._HANDLERS
    ]
    assert missing == []


def test_every_installable_kind_is_a_known_kind():
    unknown = [k for k in installer._HANDLERS if k not in manifest.KINDS]
    assert unknown == []


# ── round trip through install + publish ────────────────────────────


CONFIGS = {
    "preproc_config": (
        "pipeline_store",
        yaml.safe_dump({
            "name": "incoming", "nodes": [{"id": "ident", "type": "identity"}],
            "edges": [], "manifest": {"backend_node": "ident"},
        }),
    ),
    "autoflatten_config": (
        "autoflatten_config_store",
        yaml.safe_dump({"autoflatten": {
            "subject": "sub-01", "subjects_dir": "/fs",
        }}),
    ),
}


@pytest.fixture
def state(tmp_path, monkeypatch):
    from fmriflow.core import paths
    from fmriflow.server.services.autoflatten_config_store import AutoflattenConfigStore
    from fmriflow.server.services.convert_config_store import ConvertConfigStore
    from fmriflow.server.services.pipeline_store import PipelineStore

    monkeypatch.setenv("FMRIFLOW_HOME", str(tmp_path))
    monkeypatch.setattr(paths, "RUNTIME_CONFIG_PATH", tmp_path / "settings.json")

    return SimpleNamespace(
        convert_config_store=ConvertConfigStore(paths.config_dir("convert")),
        pipeline_store=PipelineStore(paths.config_dir("preproc")),
        autoflatten_config_store=AutoflattenConfigStore(paths.config_dir("autoflatten")),
    )


@pytest.mark.parametrize("kind", sorted(CONFIGS))
def test_install_then_locate_round_trip(kind, state, tmp_path):
    store_attr, text = CONFIGS[kind]
    src = tmp_path / "incoming.yaml"
    src.write_text(text)
    entry = manifest.ArtifactEntry(kind=kind, name="incoming.yaml", files=[], sha256="")

    res = installer._HANDLERS[kind](entry, [src], state)
    assert Path(res["path"]).is_file()

    # Visible as installed, and findable again for publishing.
    assert "incoming.yaml" in installer.local_names(kind, state)
    found, _meta = publisher.locate_local(kind, "incoming.yaml", state)
    assert found[0].read_text() == text


@pytest.mark.parametrize("kind", sorted(CONFIGS))
def test_install_rejects_the_wrong_section(kind, state, tmp_path):
    """A YAML without the stage's top-level key must fail loudly.

    The stores report this by returning errors rather than raising, so an
    unchecked call would report success having written nothing.
    """
    src = tmp_path / "wrong.yaml"
    src.write_text(yaml.safe_dump({"something_else": {"a": 1}}))
    entry = manifest.ArtifactEntry(kind=kind, name="wrong.yaml", files=[], sha256="")

    with pytest.raises(installer.InstallError):
        installer._HANDLERS[kind](entry, [src], state)


def test_convert_config_install_round_trip(state, tmp_path):
    text = yaml.safe_dump({
        "source_dir": "/dicoms", "bids_dir": "/bids",
        "subject": "01", "heuristic": "mp2rage_anat",
    })
    src = tmp_path / "conv.yaml"
    src.write_text(text)
    entry = manifest.ArtifactEntry(
        kind="convert_config", name="conv.yaml", files=[], sha256="",
    )

    res = installer._install_convert_config(entry, [src], state)
    # Written verbatim — the store's own save_config would inject _meta
    # and rewrite the filename.
    assert Path(res["path"]).read_text() == text
    assert "conv.yaml" in installer.local_names("convert_config", state)


def test_convert_config_install_requires_the_core_fields(state, tmp_path):
    src = tmp_path / "conv.yaml"
    src.write_text(yaml.safe_dump({"source_dir": "/dicoms"}))
    entry = manifest.ArtifactEntry(
        kind="convert_config", name="conv.yaml", files=[], sha256="",
    )

    with pytest.raises(installer.InstallError, match="missing required field"):
        installer._install_convert_config(entry, [src], state)


def test_convert_config_accepts_a_batch_config(state, tmp_path):
    """Batch configs carry jobs instead of the single-subject fields."""
    src = tmp_path / "batch.yaml"
    src.write_text(yaml.safe_dump({
        "convert_batch": {"heuristic": "mp2rage_anat", "bids_dir": "/bids"},
    }))
    entry = manifest.ArtifactEntry(
        kind="convert_config", name="batch.yaml", files=[], sha256="",
    )

    res = installer._install_convert_config(entry, [src], state)
    assert Path(res["path"]).is_file()


@pytest.mark.parametrize("kind", STAGE_CONFIG_KINDS)
def test_publishing_something_absent_raises(kind, state):
    with pytest.raises(PublishError):
        publisher.locate_local(kind, "nope.yaml", state)


def test_convert_get_config_returns_none_for_missing_file(state):
    """Regression: this used to raise NameError on an undefined LEGACY_DIR."""
    assert state.convert_config_store.get_config("absent.yaml") is None


def test_convert_get_config_reaches_every_scanned_legacy_root(state, tmp_path):
    """Anything list_configs advertises must be fetchable.

    The store scans two legacy roots but get_config only fell back to
    one, so publishing a config discovered in the other failed with
    "no local convert config".
    """
    text = yaml.safe_dump({
        "source_dir": "/d", "bids_dir": "/b", "subject": "01", "heuristic": "h",
    })
    store = state.convert_config_store

    # Point both legacy roots inside tmp_path — the real ones include a
    # CWD-relative ./experiments/convert we must not write to.
    legacy_a, legacy_b = tmp_path / "legacy_a", tmp_path / "legacy_b"
    store._legacy_dirs = [legacy_a, legacy_b]

    for legacy_dir in (legacy_a, legacy_b):
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "legacy_probe.yaml").write_text(text)
        store._invalidate()

        listed = {c["filename"] for c in store.list_configs()}
        assert "legacy_probe.yaml" in listed, f"not listed from {legacy_dir.name}"

        found, _ = publisher.locate_local("convert_config", "legacy_probe.yaml", state)
        assert found[0].read_text() == text

        (legacy_dir / "legacy_probe.yaml").unlink()
        store._invalidate()
