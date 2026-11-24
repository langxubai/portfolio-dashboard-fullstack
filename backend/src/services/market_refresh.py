"""Coalesce manual and scheduled refreshes into one observable background run."""

from copy import deepcopy
import logging
import threading
import time
from uuid import uuid4

from src.services.market_collector import refresh_market_quotes
from src.services.market_store import utc_now_iso

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_state = {"status": "idle", "id": None, "results": []}
_finished_monotonic = 0.0


def get_refresh_status():
    with _lock:
        return deepcopy(_state)


def _run():
    global _finished_monotonic
    try:
        results = refresh_market_quotes()
    except Exception as exc:
        logger.exception("Market refresh failed")
        results = [{"symbol": "更新任务", "ok": False, "error": type(exc).__name__}]
    successes = sum(bool(result["ok"]) for result in results)
    with _lock:
        _state.update({
            "status": "completed" if successes == len(results) else "partial" if successes else "failed",
            "finished_at": utc_now_iso(), "results": results,
            "succeeded": successes, "failed": len(results) - successes,
        })
        _finished_monotonic = time.monotonic()


def request_market_refresh():
    with _lock:
        if _state["status"] == "running" or (_finished_monotonic and time.monotonic() - _finished_monotonic < 15):
            return deepcopy(_state)
        _state.clear()
        _state.update({"id": str(uuid4()), "status": "running", "started_at": utc_now_iso(),
                       "finished_at": None, "results": [], "succeeded": 0, "failed": 0})
        threading.Thread(target=_run, name="market-refresh", daemon=True).start()
        return deepcopy(_state)
