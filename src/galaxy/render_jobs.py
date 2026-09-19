"""Thread-safe background scene rendering with cooperative cancellation."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable

from .pipeline import PipelineCancelled
from .scene_card import load_scene
from .scene_pipeline import ScenePipelineResult, run_scene_pipeline
from .scene_workflow import OperationPhase


RenderRunner = Callable[..., ScenePipelineResult]


@dataclass(frozen=True, slots=True)
class RenderJobSnapshot:
    phase: OperationPhase
    launched_revision: int
    stage: str
    message: str
    result: ScenePipelineResult | None


@dataclass(slots=True)
class RenderJob:
    card_path: Path
    launched_revision: int
    _runner: RenderRunner = field(repr=False)
    _phase: OperationPhase = field(default=OperationPhase.IDLE, init=False, repr=False)
    _stage: str = field(default="", init=False, repr=False)
    _message: str = field(default="", init=False, repr=False)
    _result: ScenePipelineResult | None = field(default=None, init=False, repr=False)
    _cancel: Event = field(default_factory=Event, init=False, repr=False)
    _done: Event = field(default_factory=Event, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _thread: Thread | None = field(default=None, init=False, repr=False)

    def start(self) -> None:
        with self._lock:
            if self._phase is not OperationPhase.IDLE:
                raise RuntimeError("render job has already started")
            self._phase = OperationPhase.RUNNING
            self._thread = Thread(target=self._run, name="galaxy-render", daemon=True)
            self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    def snapshot(self) -> RenderJobSnapshot:
        with self._lock:
            return RenderJobSnapshot(
                self._phase, self.launched_revision, self._stage, self._message, self._result
            )

    def _progress(self, stage: str) -> None:
        with self._lock:
            self._stage = stage

    def _run(self) -> None:
        try:
            result = self._runner(
                self.card_path,
                progress=self._progress,
                cancel_requested=self._cancel.is_set,
            )
            with self._lock:
                self._result = result
                self._phase = OperationPhase.SUCCEEDED
                self._message = f"Preview completed for scene revision {self.launched_revision}."
        except PipelineCancelled as exc:
            with self._lock:
                self._phase = OperationPhase.CANCELLED
                self._message = str(exc)
        except Exception as exc:
            with self._lock:
                self._phase = OperationPhase.FAILED
                self._message = str(exc)
        finally:
            self._done.set()


def start_render_job(
    card_path: str | Path, *, runner: RenderRunner = run_scene_pipeline
) -> RenderJob:
    path = Path(card_path).resolve()
    job = RenderJob(path, load_scene(path).content_revision, runner)
    job.start()
    return job


def request_cancellation_before_departure(job: RenderJob | None) -> bool:
    """Request cooperative cancellation and report whether departure must wait."""
    if job is None or job.snapshot().phase is not OperationPhase.RUNNING:
        return False
    job.cancel()
    return True
