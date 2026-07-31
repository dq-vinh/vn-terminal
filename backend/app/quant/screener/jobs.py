"""Background screener execution (WP7 deliverable "Background jobs").

Section 15 and WP16 put the screener inside an unattended daily-close
routine, so it must run without blocking a caller and must report progress.
This module is the only place in `backend/app/quant/**` that starts a thread;
everything it schedules is the pure `run_screen` function, so concurrency
cannot change a result.

The design mirrors `DataService` in the data workstream: a single-worker
executor, a lock around the mutable job table, and a status vocabulary of
`queued`/`running`/`completed`/`failed` matching the illustrative values in
`screen_start_response.schema.json`. One worker rather than several is
deliberate: two concurrent full-universe screens would contend for memory
without finishing sooner, and a deterministic run order makes a failure
reproducible.

A job that raises stores the exception text and moves to `failed`. It never
stores a partial result set, because a partially screened universe looks
exactly like a fully screened one with fewer hits, and that is precisely the
kind of quiet wrongness this project is trying to avoid.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .runner import ScreenRun

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"


@dataclass
class JobRecord:
    run_id: str
    status: str = QUEUED
    run: ScreenRun | None = None
    error: str | None = None
    progress: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


class ScreenerJobs:
    """A small, explicit job table for background screener runs."""

    def __init__(self, *, max_workers: int = 1) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="vn-screener"
        )
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._futures: dict[str, Future[ScreenRun]] = {}

    def submit(
        self,
        run_id: str,
        work: Callable[[], ScreenRun],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> JobRecord:
        """Queue a run.

        Submitting a `run_id` that is already queued or running returns the
        existing record rather than starting a second identical screen. Since
        `run_id` is a hash of the run's inputs, that deduplication is exactly
        "do not run the same screen twice concurrently".
        """

        with self._lock:
            existing = self._jobs.get(run_id)
            if existing is not None and existing.status in (QUEUED, RUNNING):
                return existing
            record = JobRecord(run_id=run_id, metadata=dict(metadata or {}))
            self._jobs[run_id] = record

        def task() -> ScreenRun:
            with self._lock:
                record.status = RUNNING
            try:
                result = work()
            except BaseException as error:
                with self._lock:
                    record.status = FAILED
                    record.error = f"{type(error).__name__}: {error}"
                    record.progress = 1.0
                raise
            with self._lock:
                record.status = COMPLETED
                record.run = result
                record.progress = 1.0
            return result

        self._futures[run_id] = self._executor.submit(task)
        return record

    def status(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._jobs.get(run_id)
            return None if record is None else record.snapshot()

    def result(self, run_id: str, timeout: float | None = None) -> ScreenRun:
        future = self._futures.get(run_id)
        if future is None:
            raise KeyError(f"unknown screener run {run_id!r}")
        return future.result(timeout=timeout)

    def wait(self, run_id: str, timeout: float | None = None) -> dict[str, Any]:
        """Block until the run finishes, then return its status snapshot.

        A failed run is reported through the snapshot rather than re-raised
        here, because a caller polling for status wants the status. The
        exception itself is still available from `result()`. `Future.exception`
        is used instead of catching around `Future.result`, so the failure is
        read deliberately rather than swallowed.
        """

        future = self._futures.get(run_id)
        if future is not None:
            future.exception(timeout=timeout)
        snapshot = self.status(run_id)
        if snapshot is None:
            raise KeyError(f"unknown screener run {run_id!r}")
        return snapshot

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
