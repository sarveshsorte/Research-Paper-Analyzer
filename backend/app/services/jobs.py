"""Background jobs: a concurrency limit, a timeout, and steps saved for SSE replay."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from backend.app.adapters.providers import UpstreamError
from backend.app.adapters.query_pipeline import JobFailure
from backend.app.services.runtime import RuntimeStore, run_in_background

logger = logging.getLogger(__name__)


class StepEmitter:
    """emit(type, message, via=None): saves a §4 step with seconds since the start."""

    def __init__(self, store: RuntimeStore, job_id: str) -> None:
        self.store = store
        self.job_id = job_id
        self.started = time.monotonic()

    def __call__(self, step_type: str, message: str, via: str | None = None) -> None:
        step: dict[str, Any] = {
            "type": step_type,
            "message": message,
            "t": round(time.monotonic() - self.started, 1),
        }
        if via:
            step["via"] = via
        self.store.add_job_step(self.job_id, step)


Work = Callable[[StepEmitter], Awaitable[Any]]


class JobRunner:
    def __init__(
        self, store: RuntimeStore, *, concurrency: int, timeout: float
    ) -> None:
        self.store = store
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(concurrency)

    def start(
        self,
        kind: str,
        owner_uid: str | None,
        work: Work,
        *,
        timeout: float | None = None,
    ) -> str:
        job = self.store.create_job(kind, owner_uid)
        run_in_background(self._run(job.job_id, work, timeout or self.timeout))
        return job.job_id

    async def _run(self, job_id: str, work: Work, timeout: float) -> None:
        emit = StepEmitter(self.store, job_id)
        try:
            async with self._semaphore:
                result = await asyncio.wait_for(work(emit), timeout)
        except JobFailure as exc:
            self.store.fail_job(job_id, {"code": exc.code, "message": exc.message})
        except UpstreamError as exc:
            self.store.fail_job(job_id, {"code": "UPSTREAM_ERROR", "message": str(exc)})
        except TimeoutError:
            self.store.fail_job(
                job_id,
                {
                    "code": "UPSTREAM_ERROR",
                    "message": f"This took longer than {int(timeout)} seconds. "
                    "Try again with fewer papers.",
                },
            )
        except Exception:
            logger.exception("job_failed job_id=%s", job_id)
            self.store.fail_job(
                job_id,
                {
                    "code": "INTERNAL_ERROR",
                    "message": "Something went wrong while running this job.",
                },
            )
        else:
            self.store.finish_job(job_id, result)
