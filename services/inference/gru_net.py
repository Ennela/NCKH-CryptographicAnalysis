"""GRU architecture mirror used to rebuild the trained model from its state dict.

``mlflow.pytorch.load_model`` unpickles the module class by its original
import path (``services.training.models.gru_model``), which is only available
when the whole repo is on PYTHONPATH (dev bind mount). The inference image
ships without the training package, so the loader falls back to
reconstructing the network from the ``model_state/gru_state_dict.pt`` artifact
plus the architecture params logged on the MLflow run.

This class must stay attribute-compatible with
services/training/models/gru_model.py::GRUForecaster (``gru`` +
``output_layer``) so that ``load_state_dict`` maps 1:1, and its ``forward``
must apply the same residual head: the output layer predicts a correction
that is added to the last scaled ``close`` (feature column 0). Without the
residual term the rebuilt network would silently return the correction
alone. Parity is enforced by services/inference/tests/test_predictors.py.
"""

from __future__ import annotations

import torch
from torch import nn


class GRUForecaster(nn.Module):
    """Map a chronological feature sequence to one scaled next-close value."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        num_layers: int,
        dropout: float,
    ) -> None:
        super().__init__()
        if min(input_size, hidden_size, num_layers) <= 0:
            raise ValueError("GRU dimensions must be positive integers.")
        if not 0.0 <= dropout < 1.0:
            raise ValueError("GRU dropout must be in [0, 1).")

        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.output_layer = nn.Linear(hidden_size, 1)
        nn.init.zeros_(self.output_layer.weight)
        nn.init.zeros_(self.output_layer.bias)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        """Return one prediction per sequence as a one-dimensional tensor."""
        if inputs.ndim != 3 or inputs.shape[-1] != self.input_size:
            raise ValueError(
                "GRU inputs must have shape (batch, sequence, input_size)."
            )
        recurrent_output, _ = self.gru(inputs)
        residual = self.output_layer(recurrent_output[:, -1, :]).squeeze(-1)
        # Residual connection: close price is at index 0
        last_close = inputs[:, -1, 0]
        return last_close + residual
