from __future__ import annotations

from src.metrics import compute_metrics


def test_compute_metrics_includes_accuracy() -> None:
    # 3-class toy example with 4/6 correct.
    y_true = [0, 0, 1, 1, 2, 2]
    y_pred = [0, 1, 1, 1, 2, 0]
    classes = ["F0", "F1", "F2"]

    m = compute_metrics(y_true, y_pred, classes)
    assert 0.0 <= m.accuracy <= 1.0
    assert abs(m.accuracy - (4 / 6)) < 1e-9

