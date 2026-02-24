"""Exception hierarchy for denizenspipeline."""


class DenizensError(Exception):
    """Base error for all denizenspipeline errors."""
    pass


class ConfigError(DenizensError):
    """Invalid configuration."""

    def __init__(self, errors):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("\n".join(f"  - {e}" for e in errors))


class PluginNotFoundError(DenizensError):
    """Plugin name not in registry."""
    pass


class PipelineError(DenizensError):
    """Error during pipeline execution."""

    def __init__(self, message, stage=None):
        self.stage = stage
        super().__init__(f"[{stage}] {message}" if stage else message)


class StageError(PipelineError):
    """Error in a specific stage — wraps the original exception."""

    def __init__(self, stage, original):
        self.original = original
        super().__init__(f"Stage '{stage}' failed: {original}", stage=stage)
