"""分来源补充口径不能改写全模型指标，也不能丢掉错误的预测列。"""
import numpy as np
import pytest

from ml.agrivision_ml.experiment_report import source_metrics
from ml.agrivision_ml.train import metrics


def test_source_with_four_of_fourteen_classes_keeps_both_scopes():
    labels = [f"class-{i}" for i in range(14)]
    matrix = np.zeros((14, 14), dtype=int)
    for i in range(4):
        matrix[i, i] = 5
    result = source_metrics(matrix, labels)
    assert result["metric_scope"] == "all_model_classes"
    assert result["macro_f1"] == pytest.approx(4 / 14)
    assert result["balanced_accuracy"] == pytest.approx(4 / 14)
    assert result["present_labels"] == labels[:4]
    assert result["present_class_macro_f1"] == 1.
    assert result["present_class_balanced_accuracy"] == 1.
    assert all(result[key] == value for key, value in metrics(matrix).items())


def test_prediction_to_absent_truth_class_still_counts_as_error():
    labels = [f"class-{i}" for i in range(14)]
    matrix = np.zeros((14, 14), dtype=int)
    for i in range(4):
        matrix[i, i] = 5
    matrix[0, 0], matrix[0, 13] = 4, 1
    result = source_metrics(matrix, labels)
    assert result["accuracy"] == .95
    assert result["present_class_macro_f1"] == pytest.approx((8 / 9 + 3) / 4)
    assert result["present_class_balanced_accuracy"] == .95
    assert result["confusion_matrix"][0][13] == 1
    assert result["present_labels"] == labels[:4]
    assert all(result[key] == value for key, value in metrics(matrix).items())
