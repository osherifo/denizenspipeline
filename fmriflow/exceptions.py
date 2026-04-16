"""Exception hierarchy for fmriflow."""


class FmriflowError(Exception):
    """Base error for all fmriflow errors."""
    pass


class ConfigError(FmriflowError):
    """Invalid configuration."""

    def __init__(self, errors):
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("\n".join(f"  - {e}" for e in errors))


class ModuleLookupError(FmriflowError):
    """A pipeline module name was not found in the registry."""
    pass


class PipelineError(FmriflowError):
    """Error during pipeline execution."""

    def __init__(self, message, stage=None):
        self.stage = stage
        super().__init__(f"[{stage}] {message}" if stage else message)


class StageError(PipelineError):
    """Error in a specific stage — wraps the original exception."""

    def __init__(self, stage, original):
        self.original = original
        super().__init__(f"Stage '{stage}' failed: {original}", stage=stage)
