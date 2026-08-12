"""Tiny thread-based job manager for long-running work.

Generation, evolution, optimization and walk-forward runs execute in a
background thread; the UI polls ``/api/jobs/{id}`` and renders a progress bar.
"""

from __future__ import annotations

import os
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class Job:
    id: str
    kind: str
    status: str = "running"          # running | done | error
    progress: float = 0.0            # 0..1
    message: str = ""
    result: Any = None
    error: str = ""
    partial: Any = None              # streaming snapshot while running
    cancelled: bool = False
    owner: str | None = None         # de quién es, para el cupo por persona

    def to_dict(self, include_result: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id, "kind": self.kind, "status": self.status,
            "progress": round(self.progress, 4), "message": self.message,
        }
        if self.status == "error":
            d["error"] = self.error
        if include_result and self.status == "done":
            d["result"] = self.result
        if self.status == "running" and self.partial is not None:
            d["partial"] = self.partial
        return d


@dataclass(slots=True)
class JobHandle:
    """What a streaming worker sees: progress + live snapshots + stop flag."""

    _job: Job

    def progress(self, frac: float, msg: str = "") -> None:
        self._job.progress = max(0.0, min(1.0, frac))
        if msg:
            self._job.message = msg

    def publish(self, snapshot: Any) -> None:
        self._job.partial = snapshot

    @property
    def cancelled(self) -> bool:
        return self._job.cancelled


class DemasiadoTrabajo(Exception):
    """No hay lugar para arrancar otra búsqueda ahora mismo."""


class JobManager:
    """Corre trabajos largos en hilos, con un tope de cuántos a la vez.

    El tope no es un detalle de rendimiento. Minar es trabajo de procesador
    puro: una búsqueda ocupa un núcleo durante minutos. Sin límite, cada clic
    en "Minar" arrancaba un hilo más, así que un puñado de personas —o una sola
    impaciente apretando el botón— dejaban el servidor a paso de hombre para
    todos, incluidas las suyas propias.

    Se reparte en dos niveles. El global protege la máquina y se deja un núcleo
    libre para atender pedidos, o el servidor deja de responder mientras mina.
    El de por persona evita que alguien acapare la cola: sin él, uno solo podría
    llenar todos los lugares y el resto no entraría nunca.
    """

    def __init__(self, max_jobs: int = 50, max_running: int | None = None,
                 max_por_usuario: int = 1) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._max_jobs = max_jobs
        self._max_running = max_running or max(1, (os.cpu_count() or 2) - 1)
        self._max_por_usuario = max_por_usuario

    # ------------------------------------------------------------------ cupos
    def _corriendo(self, dueno: str | None = None) -> int:
        return sum(1 for j in self._jobs.values()
                   if j.status == "running" and (dueno is None or j.owner == dueno))

    def _tomar_lugar(self, dueno: str | None) -> None:
        """Levanta DemasiadoTrabajo si no hay lugar. Se llama con el lock puesto."""
        if self._corriendo() >= self._max_running:
            raise DemasiadoTrabajo(
                "El servidor está minando al máximo de su capacidad. "
                "Probá de nuevo en un minuto.")
        if dueno is not None and self._corriendo(dueno) >= self._max_por_usuario:
            raise DemasiadoTrabajo(
                "Ya tenés una búsqueda corriendo. Esperá a que termine "
                "o frenala antes de empezar otra.")

    def submit(self, kind: str, fn: Callable[[Callable[[float, str], None]], Any],
               dueno: str | None = None) -> str:
        """Run ``fn(progress)`` in a thread; ``progress(frac, msg)`` updates status."""
        job = Job(id=uuid.uuid4().hex[:10], kind=kind, owner=dueno)
        with self._lock:
            self._tomar_lugar(dueno)
            self._jobs[job.id] = job
            self._trim()

        def progress(frac: float, msg: str = "") -> None:
            job.progress = max(0.0, min(1.0, frac))
            if msg:
                job.message = msg

        def runner() -> None:
            try:
                job.result = fn(progress)
                job.progress = 1.0
                job.status = "done"
            except Exception as exc:  # surfaced to the UI, never crashes the server
                job.status = "error"
                job.error = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()

        threading.Thread(target=runner, daemon=True).start()
        return job.id

    def submit_streaming(self, kind: str, fn: Callable[[JobHandle], Any],
                         dueno: str | None = None) -> str:
        """Run ``fn(handle)`` in a thread; the handle streams partial snapshots
        and exposes a cooperative ``cancelled`` flag."""
        job = Job(id=uuid.uuid4().hex[:10], kind=kind, owner=dueno)
        with self._lock:
            self._tomar_lugar(dueno)
            self._jobs[job.id] = job
            self._trim()
        handle = JobHandle(job)

        def runner() -> None:
            try:
                job.result = fn(handle)
                job.progress = 1.0
                job.status = "done"
            except Exception as exc:  # surfaced to the UI, never crashes the server
                job.status = "error"
                job.error = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()

        threading.Thread(target=runner, daemon=True).start()
        return job.id

    def cancel(self, job_id: str) -> bool:
        """Request cooperative cancellation. True if the job exists."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.cancelled = True
        return True

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _trim(self) -> None:
        finished = [j for j in self._jobs.values() if j.status != "running"]
        while len(self._jobs) > self._max_jobs and finished:
            victim = finished.pop(0)
            self._jobs.pop(victim.id, None)
