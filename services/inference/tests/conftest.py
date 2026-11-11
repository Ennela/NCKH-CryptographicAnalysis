"""Test setup for services/inference.

The service uses flat module imports (``from model_loader import ...``)
because uvicorn runs from the service directory — put that directory on
sys.path before the test modules import ``main``.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))
