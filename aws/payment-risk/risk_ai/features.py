"""One feature contract for data preparation and both serving engines."""

from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ["amount_usd", "transactions_10m", "account_age_days", "country_mismatch", "failed_attempts_1h", "hour"]


class Payment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    amount_usd: float = Field(ge=0, le=100000)
    transactions_10m: int = Field(ge=0, le=100)
    account_age_days: int = Field(ge=0, le=36500)
    country_mismatch: bool
    failed_attempts_1h: int = Field(ge=0, le=100)
    hour: int = Field(ge=0, le=23)


def vector(payment: Payment) -> list[float]:
    values = payment.model_dump()
    return [float(values[name]) for name in FEATURES]


def transform(raw: np.ndarray) -> np.ndarray:
    """Reduce the wide amount/age ranges before standardization."""
    result = np.asarray(raw, dtype=np.float32).copy()
    result[:, 0] = np.log1p(result[:, 0])
    result[:, 2] = np.log1p(result[:, 2])
    return result


def normalize(raw: np.ndarray, preprocessing: dict) -> np.ndarray:
    if preprocessing["features"] != FEATURES or preprocessing["transform"] != "log1p_amount_age_v1":
        raise ValueError("Unsupported feature contract")
    mean = np.asarray(preprocessing["mean"], dtype=np.float32)
    scale = np.asarray(preprocessing["scale"], dtype=np.float32)
    if mean.shape != (len(FEATURES),) or scale.shape != mean.shape or not np.all(scale > 0):
        raise ValueError("Invalid normalization parameters")
    return (transform(raw) - mean) / scale
