"""Generated loader skeletons match how the orchestrator calls loaders: load(config)."""

import inspect

from fmriflow.server.services.templates import TEMPLATES


def _load_signature(category: str) -> list[str]:
    src = TEMPLATES[category].format(name="demo_loader", class_name="DemoLoader")
    namespace: dict = {}
    exec(compile(src, "<skeleton>", "exec"), namespace)
    from fmriflow.modules import _decorators

    try:
        cls = namespace["DemoLoader"]
        return list(inspect.signature(cls.load).parameters)
    finally:
        _decorators._stimulus_loaders.pop("demo_loader", None)
        _decorators._response_loaders.pop("demo_loader", None)


def test_stimulus_loader_skeleton_takes_config_only():
    assert _load_signature("stimulus_loaders") == ["self", "config"]


def test_response_loader_skeleton_takes_config_only():
    assert _load_signature("response_loaders") == ["self", "config"]
