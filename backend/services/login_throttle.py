"""Lightweight, in-process login throttle.

Repeated failed logins for a given email are counted; after a configurable
number of consecutive failures the account is locked out for a fixed window.
The mechanism is deterministic (a caller-supplied clock can drive it), recoverable
(the lock expires automatically and a successful login clears all state), and
requires no external infrastructure such as Redis.
"""

import math
from collections.abc import Callable
from threading import Lock
from time import monotonic


# Bound the number of tracked emails so an attacker spraying distinct addresses
# cannot grow the table without limit. When exceeded, expired/idle entries are
# pruned before a new one is recorded.
_MAX_TRACKED_EMAILS = 10_000


class LoginThrottle:
    def __init__(
        self,
        *,
        max_attempts: int,
        lockout_seconds: int,
        clock: Callable[[], float] = monotonic,
    ):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._clock = clock
        self._lock = Lock()
        self._records: dict[str, dict[str, float]] = {}

    def _now(self) -> float:
        return self._clock()

    def _is_record_active(self, record: dict[str, float]) -> bool:
        if record["failures"] > 0:
            return True

        return self._now() < record["locked_until"]

    def seconds_until_unlock(self, email: str) -> int:
        record = self._records.get(email)

        if record is None:
            return 0

        remaining = record["locked_until"] - self._now()

        if remaining <= 0:
            return 0

        return math.ceil(remaining)

    def is_locked(self, email: str) -> bool:
        return self.seconds_until_unlock(email) > 0

    def register_failure(self, email: str) -> None:
        with self._lock:
            if len(self._records) >= _MAX_TRACKED_EMAILS:
                self._prune_expired_locked()

            record = self._records.get(email)

            if record is None or not self._is_record_active(record):
                record = {"failures": 0.0, "locked_until": 0.0}
                self._records[email] = record

            record["failures"] += 1

            if record["failures"] >= self.max_attempts:
                record["locked_until"] = (
                    self._now() + self.lockout_seconds
                )
                record["failures"] = 0.0

    def reset(self, email: str) -> None:
        with self._lock:
            self._records.pop(email, None)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def _prune_expired_locked(self) -> None:
        now = self._now()

        for email in list(self._records):
            record = self._records[email]

            if record["failures"] <= 0 and record["locked_until"] <= now:
                del self._records[email]
