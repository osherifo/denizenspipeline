"""User add-on modules load in the CLI process, not only in the web server."""

from fmriflow.modules import user_modules
from fmriflow.modules._decorators import _reporters

ADDON = '''
from fmriflow.modules._decorators import reporter


@reporter("zz_test_addon_reporter")
class AddonReporter:
    name = "zz_test_addon_reporter"

    def report(self, result, context, config):
        return {}

    def validate_config(self, config):
        return []
'''


def test_cli_registry_includes_user_addons(tmp_path, monkeypatch):
    (tmp_path / "zz_test_addon.py").write_text(ADDON)
    monkeypatch.setenv("FMRIFLOW_MODULES_DIR", str(tmp_path))
    from fmriflow.cli import _build_registry

    try:
        reg = _build_registry()
        assert reg.get_reporter("zz_test_addon_reporter").name == "zz_test_addon_reporter"
    finally:
        _reporters.pop("zz_test_addon_reporter", None)


def test_server_loader_reexports_the_same_functions():
    from fmriflow.server.services import module_loader

    assert module_loader.discover_user_modules is user_modules.discover_user_modules
    assert module_loader.get_modules_dir is user_modules.get_modules_dir
