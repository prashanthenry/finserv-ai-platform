"""Load only the locally built, hash-checked model pair. No training in the API."""

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import tensorflow as tf
import torch

from risk_ai.features import Payment, normalize, vector
from risk_ai.networks import pytorch_model, pytorch_probabilities, tensorflow_probabilities


class RiskService:
    def __init__(self, artifacts: Path):
        version = json.loads((artifacts / "current.json").read_text())["bundle_version"]
        if not re.fullmatch(r"[0-9a-f]{16}", version):
            raise ValueError("Invalid bundle version")
        bundle = artifacts / version
        self.manifest = json.loads((bundle / "manifest.json").read_text())
        if self.manifest["bundle_version"] != version:
            raise ValueError("Bundle version mismatch")
        expected = self.manifest["sha256"]
        required = {"tensorflow.keras", "pytorch.pt", "preprocessing.json", "evaluation.json", "split-ids.json"}
        if set(expected) != required:
            raise ValueError("Invalid artifact file set")
        if hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()[:16] != version:
            raise ValueError("Invalid bundle digest")
        for name, digest in expected.items():
            if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Artifact integrity check failed: {name}")
        self.version = version
        self.preprocessing = json.loads((bundle / "preprocessing.json").read_text())
        self.tensorflow = tf.keras.models.load_model(bundle / "tensorflow.keras", compile=False, safe_mode=True)
        self.pytorch = pytorch_model()
        self.pytorch.load_state_dict(torch.load(bundle / "pytorch.pt", map_location="cpu", weights_only=True))
        self.pytorch.eval()

    def predict(self, payment: Payment, engine: str = "both") -> dict:
        x = normalize(np.asarray([vector(payment)], dtype=np.float32), self.preprocessing)
        predictions = {}
        for name in (("tensorflow", "pytorch") if engine == "both" else (engine,)):
            if name == "tensorflow":
                probability = float(tensorflow_probabilities(self.tensorflow, x)[0])
            elif name == "pytorch":
                probability = float(pytorch_probabilities(self.pytorch, x)[0])
            else:
                raise ValueError("Unknown engine")
            if not np.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("Invalid model probability")
            predictions[name] = {
                "score": round(probability, 6),
                "label": "review" if probability >= self.manifest["threshold"] else "low_risk",
            }
        return {"bundle_version": self.version, "synthetic_only": True,
                "threshold": self.manifest["threshold"], "predictions": predictions}
