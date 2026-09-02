from __future__ import annotations

from benchmarks.metrics import BenchmarkResult, measure_samples, percentile


def test_percentile_uses_linear_interpolation() -> None:
    values = [1.0, 2.0, 3.0, 4.0]

    assert percentile(values, 0.50) == 2.5
    assert percentile(values, 0.95) == 3.85


def test_measure_samples_returns_stable_machine_readable_fields() -> None:
    calls = 0

    def operation() -> int:
        nonlocal calls
        calls += 1
        return calls

    result = measure_samples("tiny-operation", operation, samples=3, warmups=1)

    assert isinstance(result, BenchmarkResult)
    assert calls == 4
    assert result.name == "tiny-operation"
    assert result.sample_count == 3
    assert result.p50_ms >= 0
    assert result.p95_ms >= result.p50_ms
    assert result.min_ms >= 0
    assert result.max_ms >= result.min_ms
    assert result.mean_ms >= 0
    assert result.peak_python_mb >= 0
    assert result.peak_rss_mb >= 0
    assert result.to_dict() == {
        "name": result.name,
        "sample_count": 3,
        "p50_ms": result.p50_ms,
        "p95_ms": result.p95_ms,
        "min_ms": result.min_ms,
        "max_ms": result.max_ms,
        "mean_ms": result.mean_ms,
        "peak_python_mb": result.peak_python_mb,
        "peak_rss_mb": result.peak_rss_mb,
    }
