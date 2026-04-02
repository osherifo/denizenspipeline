"""PipelineContext — shared state container for pipeline stages."""

from __future__ import annotations

import pickle
import time
from pathlib import Path
from typing import Any, TypeVar

from fmriflow.exceptions import PipelineError

T = TypeVar("T")


class PipelineContext:
    """Shared state container for pipeline stages.

    Stores stage outputs with typed access and supports checkpointing.
    """

    def __init__(self, config: dict):
        self.config = config
        self._store: dict[str, Any] = {}
        self._artifacts: dict[str, dict[str, str]] = {}
        self._timestamps: dict[str, float] = {}

    def put(self, key: str, value: Any) -> None:
        """Store a stage output."""
        self._store[key] = value
        self._timestamps[key] = time.time()

    def get(self, key: str, expected_type: type[T] | None = None) -> T:
        """Retrieve a stage output with optional type checking.

        Raises
        ------
        PipelineError
            If key not found or type mismatch.
        """
        if key not in self._store:
            raise PipelineError(
                f"'{key}' not found in context. "
                f"Was the required stage run?")
        value = self._store[key]
        if expected_type is not None and not isinstance(value, expected_type):
            raise PipelineError(
                f"Expected {expected_type.__name__}, "
                f"got {type(value).__name__}")
        return value

    def has(self, key: str) -> bool:
        """Check if a key exists in the context."""
        return key in self._store

    def add_artifacts(self, reporter_name: str,
                      artifacts: dict[str, str]) -> None:
        """Store artifacts produced by a reporter."""
        self._artifacts[reporter_name] = artifacts

    @property
    def artifacts(self) -> dict[str, dict[str, str]]:
        """All stored artifacts."""
        return dict(self._artifacts)

    # ─── Checkpointing ──────────────────────────────────────────

    def save_checkpoint(self, stage_name: str) -> Path:
        """Save context state to disk for resuming.

        Returns
        -------
        Path
            Path to the checkpoint file.
        """
        output_dir = self.config.get('reporting', {}).get('output_dir', './results')
        checkpoint_dir = Path(output_dir) / '.checkpoints'
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        path = checkpoint_dir / f'{stage_name}.pkl'
        with open(path, 'wb') as f:
            pickle.dump(self._store, f)
        return path

    @classmethod
    def from_checkpoint(cls, config: dict, stage_name: str) -> PipelineContext:
        """Resume from a previously saved checkpoint.

        Parameters
        ----------
        config : dict
            Pipeline configuration.
        stage_name : str
            Name of the stage checkpoint to restore.

        Returns
        -------
        PipelineContext
            Restored context.
        """
        ctx = cls(config)
        output_dir = config.get('reporting', {}).get('output_dir', './results')
        path = Path(output_dir) / '.checkpoints' / f'{stage_name}.pkl'
        with open(path, 'rb') as f:
            ctx._store = pickle.load(f)
        return ctx
