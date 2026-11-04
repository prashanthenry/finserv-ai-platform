"""Equivalent 6 -> 16 -> 8 -> 1 neural networks in two frameworks."""

import torch
from torch import nn

from risk_ai.features import FEATURES


def pytorch_model() -> nn.Module:
    return nn.Sequential(
        nn.Linear(len(FEATURES), 16), nn.ReLU(),
        nn.Linear(16, 8), nn.ReLU(), nn.Linear(8, 1),
    )


def tensorflow_model():
    import tensorflow as tf

    return tf.keras.Sequential([
        tf.keras.Input(shape=(len(FEATURES),)),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(8, activation="relu"),
        tf.keras.layers.Dense(1),
    ])


def pytorch_probabilities(model, x):
    model.eval()
    with torch.inference_mode():
        return torch.sigmoid(model(torch.as_tensor(x, dtype=torch.float32))).numpy().reshape(-1)


def tensorflow_probabilities(model, x):
    import tensorflow as tf

    return tf.math.sigmoid(model(x, training=False)).numpy().reshape(-1)
