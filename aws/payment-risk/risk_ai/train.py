"""Train, validate, gate and publish one versioned pair of real neural models."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import tensorflow as tf
import torch
from sklearn.model_selection import train_test_split

from risk_ai.evaluation import GATES, enforce_gate, metrics
from risk_ai.features import FEATURES, ROOT, Payment, normalize, transform, vector
from risk_ai.networks import pytorch_model, pytorch_probabilities, tensorflow_model, tensorflow_probabilities

SEED = 73
EPOCHS = 50
BATCH_SIZE = 128
THRESHOLD = 0.5


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(path: Path):
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    ids = [row["payment_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate payment IDs")
    x = np.asarray([vector(Payment(**{name: row[name] for name in FEATURES})) for row in rows], dtype=np.float32)
    y = np.asarray([int(row["risk_label"]) for row in rows], dtype=np.float32)
    if set(y) != {0, 1}:
        raise ValueError("Both binary labels are required")
    train, holdout = train_test_split(np.arange(len(y)), test_size=0.4, random_state=SEED, stratify=y)
    validation, test = train_test_split(holdout, test_size=0.5, random_state=SEED, stratify=y[holdout])
    transformed = transform(x[train])
    preprocessing = {
        "features": FEATURES, "transform": "log1p_amount_age_v1",
        "mean": transformed.mean(axis=0).tolist(),
        "scale": np.maximum(transformed.std(axis=0), 1e-6).tolist(),
    }
    return normalize(x, preprocessing), y, (train, validation, test), preprocessing, ids


def train(data: Path, output: Path) -> dict:
    tf.keras.utils.set_random_seed(SEED)
    tf.config.experimental.enable_op_determinism()
    torch.manual_seed(SEED)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    x, y, (training, validation, test), preprocessing, ids = prepare(data)
    keras_model = tensorflow_model()
    keras_model.compile(optimizer=tf.keras.optimizers.Adam(0.01),
                        loss=tf.keras.losses.BinaryCrossentropy(from_logits=True))
    torch_model = pytorch_model()
    optimizer = torch.optim.Adam(torch_model.parameters(), lr=0.01)
    loss_function = torch.nn.BCEWithLogitsLoss()
    rng = np.random.default_rng(SEED)
    history = []
    best_tf_loss = best_torch_loss = float("inf")
    best_tf_weights = best_torch_weights = None
    # Validation selects weights; the untouched test split is evaluated once afterwards.
    for epoch in range(EPOCHS):
        indices = rng.permutation(training)
        torch_model.train()
        for start in range(0, len(indices), BATCH_SIZE):
            batch = indices[start:start + BATCH_SIZE]
            keras_model.train_on_batch(x[batch], y[batch, None])
            optimizer.zero_grad(set_to_none=True)
            logits = torch_model(torch.from_numpy(x[batch]))
            loss = loss_function(logits, torch.from_numpy(y[batch, None]))
            loss.backward()
            optimizer.step()
        tf_loss = float(tf.keras.losses.binary_crossentropy(
            y[validation, None], keras_model(x[validation], training=False), from_logits=True).numpy().mean())
        torch_model.eval()
        with torch.inference_mode():
            torch_loss = float(loss_function(torch_model(torch.from_numpy(x[validation])),
                                             torch.from_numpy(y[validation, None])))
        if tf_loss < best_tf_loss:
            best_tf_loss, best_tf_weights = tf_loss, keras_model.get_weights()
        if torch_loss < best_torch_loss:
            best_torch_loss = torch_loss
            best_torch_weights = {key: value.detach().clone() for key, value in torch_model.state_dict().items()}
        history.append({"epoch": epoch + 1, "tensorflow_validation_loss": tf_loss,
                        "pytorch_validation_loss": torch_loss})
    keras_model.set_weights(best_tf_weights)
    torch_model.load_state_dict(best_torch_weights)
    report = {
        "synthetic_only": True, "threshold": THRESHOLD, "gates": GATES,
        "split_sizes": {"train": len(training), "validation": len(validation), "test": len(test)},
        "test_positive_rows": int(y[test].sum()),
        "tensorflow": metrics(y[test], tensorflow_probabilities(keras_model, x[test]), THRESHOLD),
        "pytorch": metrics(y[test], pytorch_probabilities(torch_model, x[test]), THRESHOLD),
        "history": history,
    }
    for engine in ("tensorflow", "pytorch"):
        enforce_gate(report[engine])
    output.mkdir(parents=True, exist_ok=True)
    # Stage files first. A failed gate never changes the current serving bundle.
    with tempfile.TemporaryDirectory(dir=output, prefix="staging-") as temporary:
        stage = Path(temporary)
        keras_model.save(stage / "tensorflow.keras")
        torch.save(torch_model.state_dict(), stage / "pytorch.pt")
        # Check a real serialization round trip before publishing either engine.
        restored_tf = tf.keras.models.load_model(stage / "tensorflow.keras", compile=False, safe_mode=True)
        restored_torch = pytorch_model()
        restored_torch.load_state_dict(torch.load(stage / "pytorch.pt", map_location="cpu", weights_only=True))
        np.testing.assert_allclose(tensorflow_probabilities(restored_tf, x[test]),
                                   tensorflow_probabilities(keras_model, x[test]), atol=1e-6)
        np.testing.assert_allclose(pytorch_probabilities(restored_torch, x[test]),
                                   pytorch_probabilities(torch_model, x[test]), atol=1e-6)
        (stage / "preprocessing.json").write_text(json.dumps(preprocessing, indent=2) + "\n")
        (stage / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
        split_ids = {name: [ids[i] for i in indices] for name, indices in
                     zip(("train", "validation", "test"), (training, validation, test), strict=True)}
        (stage / "split-ids.json").write_text(json.dumps(split_ids, indent=2) + "\n")
        hashes = {name: sha256(stage / name) for name in (
            "tensorflow.keras", "pytorch.pt", "preprocessing.json", "evaluation.json", "split-ids.json",
        )}
        version = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]
        manifest = {
            "bundle_version": version, "dataset_sha256": sha256(data), "seed": SEED,
            "epochs": EPOCHS, "batch_size": BATCH_SIZE, "learning_rate": 0.01,
            "threshold": THRESHOLD, "architecture": [6, 16, 8, 1], "synthetic_only": True,
            "tensorflow_version": tf.__version__, "pytorch_version": torch.__version__, "sha256": hashes,
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        destination = output / version
        if not destination.exists():
            shutil.copytree(stage, destination)
        pointer = stage / "current.json"
        pointer.write_text(json.dumps({"bundle_version": version}) + "\n")
        os.replace(pointer, output / "current.json")
    summary = {"bundle_version": version, "tensorflow": report["tensorflow"], "pytorch": report["pytorch"]}
    print("MODEL GATES PASSED: " + json.dumps(summary))
    return summary

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=Path,
        default=ROOT / "data/payments.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts",
    )
    args = parser.parse_args()

    try:
        data_path = args.data.resolve(strict=True)
        output_path = args.output.resolve()
    except (OSError, RuntimeError) as error:
        parser.error(f"Invalid filesystem path: {error}")

    data_root = (ROOT / "data").resolve()
    artifacts_root = (ROOT / "artifacts").resolve()

    if not data_path.is_relative_to(data_root):
        parser.error("--data must stay inside the project's data directory")

    if not data_path.is_file():
        parser.error("--data must reference an existing file")

    if not output_path.is_relative_to(artifacts_root):
        parser.error("--output must stay inside the project's artifacts directory")

    if output_path.exists() and not output_path.is_dir():
        parser.error("--output must reference a directory")

    train(data_path, output_path)


if __name__ == "__main__":
    main()
