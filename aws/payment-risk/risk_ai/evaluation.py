"""Fixed synthetic holdout gates: never report training accuracy as test accuracy."""

import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score

GATES = {"roc_auc": 0.95, "f1": 0.80, "recall": 0.80}


def metrics(labels, probabilities, threshold: float) -> dict:
    probabilities = np.asarray(probabilities)
    if not np.isfinite(probabilities).all():
        raise ValueError("Non-finite predictions")
    predictions = (probabilities >= threshold).astype(int)
    return {
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "average_precision": float(average_precision_score(labels, probabilities)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1]).tolist(),
    }


def enforce_gate(results: dict):
    failures = [f"{name}={results[name]:.4f} < {minimum}" for name, minimum in GATES.items()
                if not np.isfinite(results[name]) or results[name] < minimum]
    if failures:
        raise ValueError("MODEL GATE FAILED: " + "; ".join(failures))
