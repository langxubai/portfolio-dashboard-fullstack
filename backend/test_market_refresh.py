import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.services import market_collector as collector
from src.services import market_refresh as refresh
from src.services.market_process import call_provider
from src.services.market_providers import parse_tencent, reference_fx, tencent_code
from test_market_snapshot_architecture import FakeSupabase, stock_transaction
from src.services.positions import calculate_positions

STOCK = {"id": "stock", "symbol": "AAPL", "asset_type": "Stock", "currency": "USD"}
FUND = {"id": "fund", "symbol": "000001", "asset_type": "FundCN", "currency": "CNY"}
QUOTE = {"current_price": 100, "previous_close": 90, "as_of": "2026-11-10T15:00:00+00:00",
         "source": "tencent", "kind": "quote"}


class QuoteTests(unittest.TestCase):
    def test_tencent_validates_identity_currency_and_market_timezone(self):
        parts = [""] * 36
        parts[2], parts[3], parts[4] = "AAPL.OQ", "100", "90"
        parts[30], parts[35] = "2026-11-10 10:00:00", "USD"
        quote = parse_tencent('v_usAAPL="' + "~".join(parts) + '";', [STOCK])["AAPL"]
        self.assertEqual(quote["as_of"], "2026-11-10T15:00:00+00:00")
        parts[2] = "MSFT.OQ"
        self.assertEqual(parse_tencent('v_usAAPL="' + "~".join(parts) + '";', [STOCK]), {})
        self.assertIsNone(tencent_code({**STOCK, "asset_type": "Crypto"}))

    def test_fallback_runs_and_records_reason(self):
        with patch.object(collector, "call_provider", side_effect=[({}, "timeout"), ({"AAPL": {**QUOTE, "source": "yfinance"}}, None)]), patch.object(collector, "patch_asset_snapshot", return_value=None) as save:
            result = collector._quote_group([STOCK], "tencent", {})
        self.assertTrue(result[0]["ok"])
        self.assertEqual(save.call_args.args[1]["quote_fallback_reason"], "timeout")

    def test_older_fallback_keeps_existing_price_and_source(self):
        existing = {"stock": {"quote_as_of": "2026-11-10T16:00:00+00:00"}}
        with patch.object(collector, "patch_asset_snapshot", return_value=None) as save:
            result = collector._save_quote(STOCK, QUOTE, None, existing)
        self.assertFalse(result["ok"])
        self.assertNotIn("current_price", save.call_args.args[1])
        self.assertNotIn("source", save.call_args.args[1])

    def test_slow_stock_source_does_not_delay_fund_persistence(self):
        fund_saved = threading.Event()
        def provider(name, payload, timeout):
            if name == "tencent":
                self.assertTrue(fund_saved.wait(2), "stock call blocked fund collection")
                return {}, "timeout"
            if name == "fund":
                return {"000001": {**QUOTE, "source": "akshare", "kind": "nav"}}, None
            return {}, "timeout"
        def save(asset, changes):
            if asset["id"] == "fund":
                fund_saved.set()
        with patch.object(collector, "_load_assets", return_value=[STOCK, FUND]), patch.object(collector, "load_all_asset_snapshots", return_value=({}, None)), patch.object(collector, "call_provider", side_effect=provider), patch.object(collector, "patch_asset_snapshot", side_effect=save), patch.object(collector, "_fx_quotes", return_value=[]):
            results = collector.refresh_market_quotes()
        self.assertEqual({r["symbol"]: r["ok"] for r in results}, {"000001": True, "AAPL": False})

    def test_history_write_does_not_restore_old_quote(self):
        saved = {"current_price": 150, "source": "tencent", "quote_as_of": "2026-11-10T16:00:00+00:00"}
        def save(asset, changes):
            saved.update(changes)
        with patch.object(collector, "call_provider", return_value=({"AAPL": {"2026-11-09": 100}}, None)), patch.object(collector, "patch_asset_snapshot", side_effect=save):
            collector._history_group([STOCK], "yahoo_history", "max")
        self.assertEqual(saved["current_price"], 150)
        self.assertEqual(saved["source"], "tencent")
        self.assertEqual(saved["history_source"], "yahoo_history")

    def test_old_database_rows_have_unknown_market_time(self):
        snapshot = {"current_price": 120, "previous_close": 115, "source": "yfinance",
                    "quote_status": "ok", "quote_fetched_at": datetime.now(timezone.utc).isoformat()}
        with patch("src.services.positions.supabase", FakeSupabase([stock_transaction()])), patch("src.services.positions.load_asset_snapshots", return_value=({"asset-1": snapshot}, None)):
            position = calculate_positions()[0]
        self.assertIsNone(position.price_market_time)
        self.assertIsNotNone(position.price_fetched_at)

    def test_reference_fx_cross_rate_direction(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {"base": "USD", "date": "2026-11-10", "rates": {"CNY": 7, "EUR": 0.9}}
        with patch("src.services.market_providers.httpx.get", return_value=Response()):
            quotes = reference_fx(["USD", "CNY", "EUR"])
        self.assertEqual(quotes["USD/CNY"]["current_price"], 7)
        self.assertAlmostEqual(quotes["CNY/EUR"]["current_price"], 0.9 / 7)


class ExecutionTests(unittest.TestCase):
    def test_timeout_terminates_worker(self):
        real_run = subprocess.run
        with tempfile.TemporaryDirectory() as folder:
            pid_file = Path(folder) / "pid"
            code = "import os,time;from pathlib import Path;Path(" + repr(str(pid_file)) + ").write_text(str(os.getpid()));time.sleep(10)"
            def hung_worker(*args, **kwargs):
                return real_run([sys.executable, "-c", code], timeout=0.3, capture_output=True, text=True)
            with patch("src.services.market_process.subprocess.run", side_effect=hung_worker):
                started = time.monotonic()
                data, error = call_provider("hung", {}, timeout=0.3)
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(data, {})
            self.assertIn("已结束", error)
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid_file.read_text()), 0)

    def test_duplicate_refreshes_share_one_job(self):
        release, started = threading.Event(), threading.Event()
        def run():
            started.set()
            release.wait(2)
            return [{"symbol": "AAPL", "ok": True}]
        with refresh._lock:
            refresh._state.update({"status": "idle"})
            refresh._finished_monotonic = 0
        with patch.object(refresh, "refresh_market_quotes", side_effect=run) as collect:
            first = refresh.request_market_refresh()
            self.assertTrue(started.wait(1))
            second = refresh.request_market_refresh()
            self.assertEqual(first["id"], second["id"])
            release.set()
            deadline = time.monotonic() + 2
            while refresh.get_refresh_status()["status"] == "running" and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(refresh.get_refresh_status()["status"], "completed")
            self.assertEqual(collect.call_count, 1)


if __name__ == "__main__":
    unittest.main()
