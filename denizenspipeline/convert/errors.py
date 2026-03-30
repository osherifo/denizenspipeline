"""Error hierarchy for the DICOM-to-BIDS conversion module."""


class ConvertError(Exception):
    """Base for all conversion errors."""

    def __init__(self, message: str, subject: str):
        self.subject = subject
        super().__init__(message)


class HeudiconvError(ConvertError):
    """Heudiconv failed during execution."""

    def __init__(self, message: str, subject: str, returncode: int, stderr: str):
        super().__init__(message, subject)
        self.returncode = returncode
        self.stderr = stderr


class HeuristicError(ConvertError):
    """Heuristic file is invalid, not found, or incompatible."""


class ValidationError(ConvertError):
    """BIDS validation failed with hard errors."""
