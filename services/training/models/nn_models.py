import logging

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class GRUForecaster(nn.Module):
    """
    Standard PyTorch GRU model for time-series forecasting.
    Takes input of shape [batch_size, sequence_length, input_dim].
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        num_layers: int,
        output_dim: int = 1,
        dropout: float = 0.2,
    ):
        super(GRUForecaster, self).__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.gru = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )

        self.fc = nn.Linear(hidden_dim, output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Initialize hidden state
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)

        # Forward propagate GRU
        out, _ = self.gru(x, h0)

        # Decode the hidden state of the last time step
        out = self.fc(out[:, -1, :])
        return out


# ==============================================================================
# Sequence Shaping Helpers (for GRU)
# ==============================================================================


def create_sequences(
    features: np.ndarray,
    targets: np.ndarray,
    sequence_length: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Converts 2D feature array and 1D target array into windowed sequences
    suitable for recurrent neural networks.

    Input:
        features:        2D array of shape (N, num_features).
        targets:         1D array of shape (N,).
        sequence_length: number of past time-steps in each input window.

    Output:
        X: 3D array of shape (N - sequence_length, sequence_length, num_features).
        y: 1D array of shape (N - sequence_length,).

    The target for each window corresponds to the time-step immediately
    *after* the window, so there is no look-ahead bias.
    """
    if len(features) != len(targets):
        raise ValueError(
            f"features and targets must have the same length, "
            f"got {len(features)} and {len(targets)}"
        )
    if sequence_length >= len(features):
        raise ValueError(
            f"sequence_length ({sequence_length}) must be less than "
            f"data length ({len(features)})"
        )

    X: list[np.ndarray] = []
    y: list[float] = []
    for i in range(sequence_length, len(features)):
        X.append(features[i - sequence_length : i])
        y.append(targets[i])

    return np.array(X), np.array(y)
