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
    paused: bool = False
    #: puesto cuando se reanuda; el hilo espera acá en vez de sondear
    reanudar: threading.Event = field(default_factory=threading.Event)

    def to_dict(self, include_result: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id, "kind": self.kind, "status": self.status,
            "progress": round(self.progress, 4), "message": self.message,
        }
        if self.paused:
            d["paused"] = True
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

    @property
    def paused(self) -> bool:
        return self._job.paused

    def esperar(self) -> None:
        """Bloquea mientras el trabajo esté en pausa.

        El worker llama esto en su punto de corte natural. Pausar no es
        cancelar: el estado de la búsqueda —población, genomas ya vistos,
        semilla— sigue intacto en el hilo, y al reanudar continúa donde estaba
        en vez de volver a empezar.

        El `wait` tiene tope aunque haya un Event: si el pedido de cancelación
        llega mientras está pausado, nadie va a poner el evento y el hilo se
        quedaría dormido para siempre.
        """
        while self._job.paused and not self._job.cancelled:
            self._job.reanudar.wait(0.5)


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
                "Ya tenés una búsqueda abierta. Esperá a que termine o frenala "
                "antes de empezar otra — una búsqueda en pausa también ocupa "
                "el lugar, porque guarda su estado para poder continuar.")

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
        # si estaba pausado hay un hilo dormido esperando: sin esto se entera
        # recién medio segundo después, y con el `wait` sin tope, nunca
        job.paused = False
        job.reanudar.set()
        return True

    def pause(self, job_id: str, on: bool) -> bool:
        """Pausa o reanuda. True si el trabajo existe y sigue corriendo."""
        job = self._jobs.get(job_id)
        if job is None or job.status != "running":
            return False
        job.paused = on
        if on:
            job.reanudar.clear()
        else:
            job.reanudar.set()
        return True

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def hay_corriendo(self, kind: str) -> bool:
        """Si ya hay un trabajo de ese tipo en marcha.

        LO NECESITA EL CICLO. Una vuelta suya dura un minuto y un minado dura
        varios, y el minado sólo deja rastro en la base CUANDO TERMINA — así
        que sin esto el ciclo vería "hace horas que no se mina" en cada vuelta
        y lanzaría uno nuevo cada minuto hasta llenar la cola.
        """
        with self._lock:
            return any(j.kind == kind and j.status == "running"
                       for j in self._jobs.values())

    def _trim(self) -> None:
        finished = [j for j in self._jobs.values() if j.status != "running"]
        while len(self._jobs) > self._max_jobs and finished:
            victim = finished.pop(0)
            self._jobs.pop(victim.id, None)
