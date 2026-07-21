"""PyTorch GRU model for one-step next-close forecasting."""

from __future__ import annotations

from typing import Any

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

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        """Return one prediction per sequence as a one-dimensional tensor."""
        if inputs.ndim != 3 or inputs.shape[-1] != self.input_size:
            raise ValueError(
                "GRU inputs must have shape (batch, sequence, input_size)."
            )
        recurrent_output, _ = self.gru(inputs)
        return self.output_layer(recurrent_output[:, -1, :]).squeeze(-1)

    def get_config(self) -> dict[str, Any]:
        """Return the architecture metadata required to reconstruct the model."""
        return {
            "input_size": self.input_size,
            "hidden_size": self.hidden_size,
            "num_layers": self.num_layers,
            "dropout": self.dropout,
        }
