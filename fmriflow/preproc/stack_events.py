"""Stack-run event emission — JSONL events on disk, tailed by the server.

The CLI shim spawns as a detached subprocess; it can't push to an
in-memory queue on the server. Instead it writes one JSON object
per line to ``<run_dir>/events.jsonl``, flushing after each.
The server's WebSocket endpoint tails this file by tracking its
byte offset.

Event schema (all events carry ``event`` + ``timestamp``):

- ``started`` — run begins; includes subject + n_stages.
- ``stage_start`` — a stage is about to execute; includes
  ``stage_index`` (0 = bootstrap, 1..N = transforms), ``stage_name``,
  ``kind`` (``bootstrap`` | ``transform``).
- ``stage_done`` — stage completed successfully; includes
  ``cache_hit`` (bool), ``duration_s``, ``fingerprint``.
- ``stage_failed`` — stage raised; includes ``error``.
- ``completed`` — overall run finished cleanly; includes
  ``n_stages`` and total ``duration_s``.
- ``failed`` — overall run failed; includes ``errors``.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


EventDict = dict[str, Any]


class EventWriter:
    """Append-only JSONL writer. Flushes after each event so the
    server's tailer sees updates promptly.

    ``__call__`` makes the writer usable as the ``event_sink`` the
    ``StackRunner`` expects: ``writer(event)`` adds a timestamp if
    missing and appends a line.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Open in append mode so reconnects / reruns don't truncate.
        self._fh = open(self.path, "a", encoding="utf-8")

    def __call__(self, event: EventDict) -> None:
        event.setdefault("timestamp", time.time())
        try:
            self._fh.write(json.dumps(event, default=str) + "\n")
            self._fh.flush()
        except Exception:
            # Never let event emission break the run.
            logger.exception("Could not write event to %s", self.path)

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def __enter__(self) -> "EventWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# Type alias for callers that want to take any callable.
EventSink = Callable[[EventDict], None]
