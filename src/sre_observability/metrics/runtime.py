"""
Python runtime metrics: CPU, memory, GC, threads, file descriptors.

All metrics carry the standard base labels from ObservabilityConfig.
A background thread refreshes gauge values every `interval` seconds.
"""
from __future__ import annotations

import gc
import logging
import threading
import time
from typing import TYPE_CHECKING

import psutil
import prometheus_client as prom

if TYPE_CHECKING:
    from sre_observability.config import ObservabilityConfig

logger = logging.getLogger(__name__)

_LABEL_NAMES = ["application", "namespace", "environment", "version"]


class RuntimeMetricsCollector:
    """Collects Python process runtime metrics and exposes them to Prometheus."""

    def __init__(self, config: "ObservabilityConfig", interval: float = 15.0) -> None:
        self._config = config
        self._interval = interval
        self._process = psutil.Process()
        self._labels = list(config.base_labels().values())
        self._running = False
        self._thread: threading.Thread | None = None

        self._init_gauges()

    # ------------------------------------------------------------------
    # Gauge definitions
    # ------------------------------------------------------------------
    def _init_gauges(self) -> None:
        kw = dict(labelnames=_LABEL_NAMES, registry=prom.REGISTRY)

        # CPU
        self.cpu_usage_percent = prom.Gauge(
            "process_cpu_usage_percent",
            "CPU usage percent of the current process",
            **kw,
        )
        # Memory
        self.mem_rss_bytes = prom.Gauge(
            "process_memory_rss_bytes",
            "Resident set size memory in bytes",
            **kw,
        )
        self.mem_vms_bytes = prom.Gauge(
            "process_memory_vms_bytes",
            "Virtual memory size in bytes",
            **kw,
        )
        self.mem_percent = prom.Gauge(
            "process_memory_percent",
            "Memory usage as a percentage of total system memory",
            **kw,
        )
        # Threads & file descriptors
        self.thread_count = prom.Gauge(
            "process_thread_count",
            "Number of threads in the current process",
            **kw,
        )
        self.open_fds = prom.Gauge(
            "process_open_fds",
            "Number of open file descriptors",
            **kw,
        )
        # GC
        self.gc_objects = prom.Gauge(
            "process_gc_objects_total",
            "Total number of objects tracked by the garbage collector",
            **kw,
        )
        self.gc_collections = prom.Counter(
            "process_gc_collections_total",
            "Total number of GC collection runs",
            labelnames=_LABEL_NAMES + ["generation"],
            registry=prom.REGISTRY,
        )
        # Uptime
        self.uptime_seconds = prom.Counter(
            "process_uptime_seconds_total",
            "Process uptime in seconds (monotonically increasing)",
            **kw,
        )
        self._start_time = time.monotonic()
        self._last_uptime_update = self._start_time

        # GC counters baseline
        self._gc_baseline = list(gc.get_count())

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------
    def collect(self) -> None:
        """Refresh all gauge values once."""
        try:
            with self._process.oneshot():
                cpu = self._process.cpu_percent(interval=None)
                mem = self._process.memory_info()
                mem_pct = self._process.memory_percent()
                n_threads = self._process.num_threads()
                try:
                    n_fds = self._process.num_fds()
                except AttributeError:
                    n_fds = -1  # Windows

            self.cpu_usage_percent.labels(*self._labels).set(cpu)
            self.mem_rss_bytes.labels(*self._labels).set(mem.rss)
            self.mem_vms_bytes.labels(*self._labels).set(mem.vms)
            self.mem_percent.labels(*self._labels).set(mem_pct)
            self.thread_count.labels(*self._labels).set(n_threads)
            self.open_fds.labels(*self._labels).set(n_fds)

            # GC
            total_objects = sum(gc.get_count())
            self.gc_objects.labels(*self._labels).set(total_objects)

            current_gc = list(gc.get_count())
            for gen, (cur, base) in enumerate(zip(current_gc, self._gc_baseline)):
                delta = cur - base
                if delta > 0:
                    self.gc_collections.labels(*self._labels, str(gen)).inc(delta)
            self._gc_baseline = current_gc

            # Uptime
            now = time.monotonic()
            self.uptime_seconds.labels(*self._labels).inc(now - self._last_uptime_update)
            self._last_uptime_update = now

        except Exception:
            logger.exception("Failed to collect runtime metrics")

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start background collection thread."""
        if self._running:
            return
        # warm up cpu_percent (first call always returns 0.0)
        self._process.cpu_percent(interval=None)
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="sre-runtime-metrics", daemon=True
        )
        self._thread.start()
        logger.info("Runtime metrics collector started (interval=%.1fs)", self._interval)

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            self.collect()
            time.sleep(self._interval)
