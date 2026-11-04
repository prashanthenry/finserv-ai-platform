"""Generate reproducible, entirely synthetic labeled payments. No customer data."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from risk_ai.features import FEATURES, ROOT


def generate(path: Path, count: int = 6000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    risky = 0
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["payment_id", *FEATURES, "risk_label"])
        writer.writeheader()
        for index in range(count):
            amount = round(float(np.clip(rng.lognormal(5.5, 1.1), 1, 100000)), 2)
            frequency = int(min(rng.poisson(3), 100))
            age = int(rng.integers(1, 1826))
            mismatch = int(rng.random() < 0.18)
            failures = int(min(rng.poisson(0.7), 100))
            hour = int(rng.integers(0, 24))
            # A deliberately learnable toy rule plus noise, not a real fraud definition.
            score = (-3.4 + np.log1p(amount / 300) + 0.35 * frequency + 1.7 * mismatch
                     + 0.9 * failures - 0.0012 * age + (hour < 6) + rng.normal(0, 0.4))
            label = int(score > 0)
            risky += label
            writer.writerow(dict(zip(
                ["payment_id", *FEATURES, "risk_label"],
                [f"SYN-{index:06d}", amount, frequency, age, mismatch, failures, hour, label], strict=True,
            )))
    metadata = {
        "synthetic": True, "generator_version": 1, "seed": seed, "rows": count,
        "positive_rows": risky, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    path.with_suffix(".meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data/payments.csv")
    args = parser.parse_args()
    print(json.dumps(generate(args.output)))


if __name__ == "__main__":
    main()
