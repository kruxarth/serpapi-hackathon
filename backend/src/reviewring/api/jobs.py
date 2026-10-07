"""Run analyses one at a time in a background worker, with an event log per analysis."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .. import db, redact
from ..collect import Collector, CollectParams, Event
from ..report import store_report
from ..serp.gateway import Gateway

log = logging.getLogger(__name__)
TERMINAL = {"done", "cancelled", "error", "paused", "needs_input"}


@dataclass
class Job:
    analysis_id: str
    input_text: str
    params: CollectParams
    mode: str
    events: list[dict[str, Any]] = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)
    finished: bool = False


class JobManager:
    def __init__(self, gateway_factory: Callable[[str], Gateway]) -> None:
        self.gateway_factory = gateway_factory
        self.jobs: dict[str, Job] = {}
        self.cond = threading.Condition()
        self.queue: queue.Queue[str] = queue.Queue()
        self.worker = threading.Thread(target=self._loop, name="reviewring-jobs", daemon=True)
        self.worker.start()

    # ------------------------------------------------------------------ public

    def submit(self, input_text: str, params: CollectParams, mode: str, analysis_id: str | None = None) -> str:
        gw = self.gateway_factory(mode)
        collector = Collector(gw, input_text, params, analysis_id=analysis_id)  # creates the row
        job = Job(collector.analysis_id, input_text, collector.params, mode)
        with self.cond:
            old = self.jobs.get(job.analysis_id)
            if old is not None and not old.finished:
                return job.analysis_id
            self.jobs[job.analysis_id] = job
            self._push(
                job,
                {
                    "type": "queued",
                    "message": "Queued",
                    "searches_used": collector.searches_used(),
                    "data": {"position": self.queue.qsize()},
                    "at": db.iso(db.utcnow()),
                },
            )
        conn = db.connect()
        conn.execute("UPDATE analyses SET status = 'queued', mode = ? WHERE id = ?", (mode, job.analysis_id))
        self.queue.put(job.analysis_id)
        return job.analysis_id

    def cancel(self, analysis_id: str) -> bool:
        with self.cond:
            job = self.jobs.get(analysis_id)
        if job and not job.finished:
            job.cancel.set()
            return True
        from ..collect import cancel_analysis

        return cancel_analysis(analysis_id)

    def events_since(self, analysis_id: str, index: int, timeout: float) -> tuple[list[dict[str, Any]], bool]:
        """Events after ``index``; waits up to ``timeout`` for new ones. Returns (events, finished)."""
        with self.cond:
            job = self.jobs.get(analysis_id)
            if job is None:
                return [], True
            if len(job.events) <= index and not job.finished:
                self.cond.wait(timeout)
            return list(job.events[index:]), job.finished

    def known(self, analysis_id: str) -> bool:
        return analysis_id in self.jobs

    # ------------------------------------------------------------------ worker

    def _push(self, job: Job, event: dict[str, Any]) -> None:
        with self.cond:
            job.events.append(event)
            if event["type"] in TERMINAL:
                job.finished = True
            self.cond.notify_all()

    def _loop(self) -> None:
        while True:
            analysis_id = self.queue.get()
            job = self.jobs.get(analysis_id)
            if job is None:
                continue
            try:
                self._run(job)
            except Exception as exc:  # noqa: BLE001 - a crash must end the job, never the worker
                log.error("analysis %s crashed: %s", analysis_id, redact.safe_error(exc))
                db.connect().execute(
                    "UPDATE analyses SET status = 'error', error = ? WHERE id = ?",
                    (redact.safe_error(exc), analysis_id),
                )
                self._push(
                    job,
                    {
                        "type": "error",
                        "message": f"Analysis failed: {redact.safe_error(exc)}",
                        "searches_used": 0,
                        "data": {},
                        "at": db.iso(db.utcnow()),
                    },
                )

    def _run(self, job: Job) -> None:
        if job.cancel.is_set():
            self._push(
                job,
                {
                    "type": "cancelled",
                    "message": "Cancelled before it started.",
                    "searches_used": 0,
                    "data": {},
                    "at": db.iso(db.utcnow()),
                },
            )
            db.connect().execute("UPDATE analyses SET status = 'cancelled' WHERE id = ?", (job.analysis_id,))
            return
        gw = self.gateway_factory(job.mode)
        if gw.live:
            gw.refresh_account()

        def on_event(e: Event) -> None:
            if e.type not in TERMINAL:  # terminal events are pushed below, once the outcome is stored
                self._push(job, e.as_dict())

        collector = Collector(
            gw, job.input_text, job.params, analysis_id=job.analysis_id, on_event=on_event, cancel=job.cancel
        )
        outcome = collector.run()
        used = collector.searches_used()
        if outcome.status != "done":
            data: dict[str, Any] = {}
            if outcome.status == "paused":
                data["resume_at"] = db.iso(outcome.resume_at) if outcome.resume_at else None
            if outcome.status == "needs_input":
                data["candidates"] = outcome.candidates
            self._push(
                job,
                {
                    "type": outcome.status,
                    "message": outcome.message,
                    "searches_used": used,
                    "data": data,
                    "at": db.iso(db.utcnow()),
                },
            )
            return
        self._push(
            job,
            {
                "type": "finding_groups",
                "message": "Finding groups",
                "searches_used": used,
                "data": {},
                "at": db.iso(db.utcnow()),
            },
        )

        def progress(message: str) -> None:
            self._push(
                job,
                {
                    "type": "reading_texts",
                    "message": message,
                    "searches_used": used,
                    "data": {},
                    "at": db.iso(db.utcnow()),
                },
            )

        report = store_report(job.analysis_id, outcome.input, job.mode, progress)
        self._push(
            job,
            {
                "type": "done",
                "message": "Done",
                "searches_used": used,
                "data": {"level": report["level"]["level"]},
                "at": db.iso(db.utcnow()),
            },
        )
