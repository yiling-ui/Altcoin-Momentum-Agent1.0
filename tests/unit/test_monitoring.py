"""Monitoring skeleton tests."""

from __future__ import annotations

from app.core.enums import IncidentLevel
from app.monitoring.alerts import Alert, AlertSink
from app.monitoring.health import HealthChecker, HealthStatus
from app.monitoring.metrics import MetricsRegistry


def test_metrics_counters_and_gauges():
    m = MetricsRegistry()
    m.incr("orders_total")
    m.incr("orders_total", 2)
    m.set_gauge("equity", 1234.5)
    snap = m.snapshot()
    assert snap["counters"]["orders_total"] == 3
    assert snap["gauges"]["equity"] == 1234.5


def test_health_aggregates_worst():
    h = HealthChecker()
    h.register("a", lambda: HealthStatus.OK)
    h.register("b", lambda: HealthStatus.DEGRADED)
    h.register("c", lambda: HealthStatus.OK)
    overall, results = h.evaluate()
    assert overall is HealthStatus.DEGRADED
    assert results["b"] is HealthStatus.DEGRADED


def test_health_handles_probe_exception():
    h = HealthChecker()

    def boom() -> HealthStatus:
        raise RuntimeError("nope")

    h.register("crash", boom)
    overall, results = h.evaluate()
    assert overall is HealthStatus.DOWN
    assert results["crash"] is HealthStatus.DOWN


def test_alert_sink_drain():
    sink = AlertSink()
    sink.emit(Alert(level=IncidentLevel.P0, title="ghost position"))
    drained = sink.drain()
    assert len(drained) == 1
    assert drained[0].level is IncidentLevel.P0
    assert sink.drain() == []
