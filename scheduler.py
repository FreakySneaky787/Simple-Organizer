# scheduler.py
"""Background auto-organise scheduler for Simple Organizer.

Uses a daemon threading.Timer to fire a callback on a fixed interval.
Thread-safe start/stop/reconfigure.

Fixes applied:
  S1 — exceptions in _fire() are now logged via log_callback instead of silently swallowed.
  S2 — timer drift corrected by computing delay relative to the intended next fire time.
  S3 — every timer carries a generation number; a timer from before a configure()/stop()
       can no longer re-arm itself, so there is never more than one live timer.
  S4 — slots missed while the computer slept are skipped instead of fired back to back.
"""

import threading
import time
from typing import Callable


class OrganizerScheduler:
    """Fires callback on a fixed interval. Start/stop/reconfigure are thread-safe."""

    def __init__(
        self,
        callback: Callable[[], None],
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._callback     = callback
        self._log_callback = log_callback
        self._interval     = 60    # minutes
        self._enabled      = False
        self._timer: threading.Timer | None = None
        self._lock         = threading.Lock()
        self._next_fire: float = 0.0   # S2: absolute monotonic time of next intended fire
        self._generation   = 0         # S3: bumped on every configure()/stop()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def interval_minutes(self) -> int:
        return self._interval

    def configure(self, interval_minutes: int, enabled: bool) -> None:
        """Update interval and enabled state. Restarts timer if running."""
        with self._lock:
            self._interval = max(1, int(interval_minutes))
            self._enabled  = enabled
            self._cancel()
            if enabled:
                self._arm_from_now()

    def stop(self) -> None:
        """Cancel any pending scheduled run. Safe to call from any thread."""
        with self._lock:
            self._enabled = False
            self._cancel()

    # ------------------------------------------------------------------

    def _cancel(self) -> None:
        """Cancel the live timer and invalidate any timer that is already firing."""
        self._generation += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _start_timer(self, delay: float) -> None:
        self._timer = threading.Timer(delay, self._fire, args=(self._generation,))
        self._timer.daemon = True
        self._timer.start()

    def _arm_from_now(self) -> None:
        """Schedule next fire exactly interval_minutes from now."""
        self._next_fire = time.monotonic() + self._interval * 60
        self._start_timer(self._interval * 60)

    def _arm_drift_corrected(self) -> None:
        """S2: Schedule next fire relative to intended time, not actual fire time.

        This prevents drift accumulating over many iterations. S4: if one or
        more slots already lie in the past (e.g. after standby), jump to the
        next future slot instead of firing once per missed slot.
        """
        now      = time.monotonic()
        interval = self._interval * 60
        self._next_fire += interval
        if self._next_fire <= now:
            missed = int((now - self._next_fire) // interval) + 1
            self._next_fire += missed * interval
        self._start_timer(max(0.0, self._next_fire - now))

    def _fire(self, generation: int) -> None:
        with self._lock:
            if not self._enabled or generation != self._generation:
                return
        try:
            self._callback()
        except Exception as exc:  # S1: log instead of swallowing silently
            if self._log_callback:
                try:
                    self._log_callback(f"[SCHEDULE ERROR]  {exc}")
                except Exception:
                    pass
        with self._lock:
            # S3: configure()/stop() during the callback already armed (or
            # cancelled) a timer of a newer generation -- do not add a second one.
            if self._enabled and generation == self._generation:
                self._arm_drift_corrected()
