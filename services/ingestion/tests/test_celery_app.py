"""The Celery app must give every forked worker its own DB connections."""

from __future__ import annotations

from typing import Any

import pytest
from celery.signals import worker_process_init

from services.ingestion import celery_app as celery_module


def test_post_fork_handler_is_connected_to_worker_process_init() -> None:
    receivers = [ref() for _, ref in worker_process_init.receivers]
    assert celery_module.reset_db_pool_after_fork in receivers


def test_post_fork_handler_drops_the_inherited_pool_without_closing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        celery_module.sync_engine, "dispose", lambda **kwargs: calls.append(kwargs)
    )
    worker_process_init.send(sender=None)
    # The suite imports this module both as "celery_app" (tasks.py) and as
    # "services.ingestion.celery_app", so the handler may run once per copy.
    assert calls
    assert all(call == {"close": False} for call in calls)
