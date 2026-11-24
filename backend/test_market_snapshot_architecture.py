import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd

from src.services.market_data import _extract_close_series
from src.services.market_collector import refresh_market_quotes
from src.services.positions import calculate_positions


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def execute(self):
        return FakeResponse(self.rows)


class FakeSupabase:
    def __init__(self, transactions):
        self.transactions = transactions

    def table(self, name):
        if name != "transactions":
            raise AssertionError(f"Unexpected table read: {name}")
        return FakeQuery(self.transactions)


def stock_transaction():
    return {
        "account_id": "account-1",
        "asset_id": "asset-1",
        "trade_type": "BUY",
        "quantity": "2",
        "price": "100",
        "trade_time": "2026-01-01T00:00:00+00:00",
        "assets": {
            "id": "asset-1",
            "symbol": "TEST",
            "name": "Test Asset",
            "asset_type": "Stock",
            "currency": "USD",
        },
    }


class MarketDataParsingTests(unittest.TestCase):
    def test_extracts_ticker_first_yfinance_layout(self):
        columns = pd.MultiIndex.from_tuples(
            [("TEST", "Close"), ("TEST", "Open")]
        )
        frame = pd.DataFrame(
            [[10.0, 9.0], [11.0, 10.0]],
            columns=columns,
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )
        self.assertEqual(_extract_close_series(frame, "TEST").tolist(), [10.0, 11.0])

    def test_extracts_price_first_yfinance_layout(self):
        columns = pd.MultiIndex.from_tuples(
            [("Close", "TEST"), ("Open", "TEST")]
        )
        frame = pd.DataFrame(
            [[10.0, 9.0], [11.0, 10.0]],
            columns=columns,
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )
        self.assertEqual(_extract_close_series(frame, "TEST").tolist(), [10.0, 11.0])


class PositionSnapshotTests(unittest.TestCase):
    def test_position_uses_last_good_snapshot_when_refresh_failed(self):
        now = datetime.now(timezone.utc).isoformat()
        snapshot = {
            "asset_id": "asset-1",
            "current_price": "120",
            "previous_close": "115",
            "source": "yfinance",
            "quote_status": "error",
            "quote_error": "Yahoo timeout",
            "quote_fetched_at": now,
        }
        with patch(
            "src.services.positions.supabase",
            FakeSupabase([stock_transaction()]),
        ), patch(
            "src.services.positions.load_asset_snapshots",
            return_value=({"asset-1": snapshot}, None),
        ):
            positions = calculate_positions()

        self.assertEqual(len(positions), 1)
        position = positions[0]
        self.assertEqual(float(position.current_value), 240.0)
        self.assertEqual(position.price_status, "stale")
        self.assertEqual(position.price_error, "Yahoo timeout")

    def test_missing_snapshot_is_not_valued_at_zero(self):
        with patch(
            "src.services.positions.supabase",
            FakeSupabase([stock_transaction()]),
        ), patch(
            "src.services.positions.load_asset_snapshots",
            return_value=({}, "snapshot table missing"),
        ):
            positions = calculate_positions()

        position = positions[0]
        self.assertIsNone(position.current_price)
        self.assertIsNone(position.current_value)
        self.assertEqual(position.price_status, "unavailable")
        self.assertEqual(position.price_error, "snapshot table missing")


class CollectorIsolationTests(unittest.TestCase):
    def test_collector_does_not_call_provider_before_schema_is_ready(self):
        asset = stock_transaction()["assets"]
        with patch(
            "src.services.market_collector._load_assets",
            return_value=[asset],
        ), patch(
            "src.services.market_collector.load_all_asset_snapshots",
            return_value=({}, "snapshot table missing"),
        ), patch(
            "src.services.market_collector.call_provider",
        ) as provider:
            refresh_market_quotes()

        provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
