"""UICaptureProxy — captures pipeline UI events for WebSocket streaming."""

from __future__ import annotations

import queue
import time

from fmriflow import ui


class UICaptureProxy:
    """Patches ui module functions to capture stage events into a queue.

    Used by RunManager to stream live pipeline progress to WebSocket clients.
    """

    CAPTURE_FUNCTIONS = (
        'stage_start', 'stage_done', 'stage_fail', 'stage_warn',
        'feature_info', 'data_warning',
    )

    def __init__(self, event_queue: queue.Queue):
        self.event_queue = event_queue
        self._originals: dict[str, object] = {}

    def install(self) -> None:
        """Patch ui module functions to capture events."""
        for name in self.CAPTURE_FUNCTIONS:
            original = getattr(ui, name, None)
            if original is not None:
                self._originals[name] = original
                setattr(ui, name, self._make_wrapper(name, original))

    def uninstall(self) -> None:
        """Restore original ui module functions."""
        for name, original in self._originals.items():
            setattr(ui, name, original)
        self._originals.clear()

    def _make_wrapper(self, fn_name: str, original):
        eq = self.event_queue

        def wrapper(*args, **kwargs):
            result = original(*args, **kwargs)

            # Build event dict based on function name
            event = {'event': fn_name, 'timestamp': time.time()}

            if fn_name == 'stage_start':
                event['stage'] = args[0] if args else ''
                event['t0'] = result  # stage_start returns t0

            elif fn_name == 'stage_done':
                event['stage'] = args[0] if args else ''
                if len(args) > 1:
                    event['elapsed'] = round(time.time() - args[1], 3)
                event['detail'] = args[2] if len(args) > 2 else kwargs.get('detail', '')

            elif fn_name == 'stage_fail':
                event['stage'] = args[0] if args else ''
                if len(args) > 1:
                    event['elapsed'] = round(time.time() - args[1], 3)
                event['error'] = args[2] if len(args) > 2 else kwargs.get('error', '')

            elif fn_name == 'stage_warn':
                event['stage'] = args[0] if args else ''
                if len(args) > 1:
                    event['elapsed'] = round(time.time() - args[1], 3)
                event['detail'] = args[2] if len(args) > 2 else kwargs.get('detail', '')

            elif fn_name == 'feature_info':
                event['name'] = args[0] if args else ''
                event['source'] = args[1] if len(args) > 1 else ''

            elif fn_name == 'data_warning':
                event['message'] = args[0] if args else ''

            eq.put(event)
            return result

        return wrapper
