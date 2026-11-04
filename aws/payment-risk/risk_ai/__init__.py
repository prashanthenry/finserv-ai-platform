"""CPU-only TensorFlow and PyTorch payment-risk learning lab."""

import os
import tempfile
from pathlib import Path

_runtime = tempfile.TemporaryDirectory(prefix="payment-risk-")
_runtime_path = Path(_runtime.name)

# Keep this small lab predictable on laptops, CI runners and Kubernetes nodes.
for name, value in {
    "CUDA_VISIBLE_DEVICES": "-1",
    "TF_CPP_MIN_LOG_LEVEL": "2",
    "TF_NUM_INTRAOP_THREADS": "1",
    "TF_NUM_INTEROP_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MPLCONFIGDIR": str(_runtime_path / "matplotlib"),
    "KERAS_HOME": str(_runtime_path / "keras"),
}.items():
    os.environ.setdefault(name, value)
