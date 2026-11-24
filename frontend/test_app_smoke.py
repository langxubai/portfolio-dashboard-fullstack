import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx
from streamlit.testing.v1 import AppTest
from api_client import api


class DashboardStubHandler(BaseHTTPRequestHandler):
    refresh_requests = 0

    def do_POST(self):
        if self.path != "/api/market/refresh":
            self.send_error(404)
            return
        type(self).refresh_requests += 1
        body = json.dumps({"id": "refresh-1", "status": "running"}).encode()
        self.send_response(202)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/positions/"):
            payload = [
                {
                    "account_id": "account-1",
                    "asset_id": "asset-1",
                    "symbol": "TEST",
                    "name": "Test Asset",
                    "asset_type": "Stock",
                    "currency": "CNY",
                    "total_quantity": "2",
                    "average_cost": 100,
                    "current_price": 120,
                    "previous_close": 115,
                    "current_value": 240,
                    "unrealized_pnl": 40,
                    "unrealized_pnl_percent": 0.2,
                    "realized_pnl": 0,
                    "realized_pnl_percent": 0,
                    "daily_pnl": 10,
                    "daily_pnl_percent": 0.0435,
                    "price_status": "ok",
                    "price_source": "yfinance",
                    "price_as_of": "2026-07-24T10:00:00+00:00",
                    "price_market_time": "2026-07-23",
                    "price_fetched_at": "2026-07-24T10:00:00+00:00",
                    "price_kind": "daily_close",
                    "price_is_stale": False,
                    "price_error": None,
                }
            ]
            template = payload[0]
            payload.extend([
                {**template, "asset_id": "closed", "symbol": "CLOSED", "name": "Closed position",
                 "total_quantity": "0.0000", "current_value": 0, "unrealized_pnl": 0,
                 "daily_pnl": 0, "realized_pnl": 14},
                {**template, "asset_id": "unpriced", "symbol": "UNPRICED", "name": "Pending quote",
                 "total_quantity": "10", "current_price": None, "current_value": None,
                 "unrealized_pnl": None, "daily_pnl": None, "price_status": "unavailable"},
                {**template, "asset_id": "usd", "symbol": "USDSTOCK", "name": "USD stock",
                 "currency": "USD", "total_quantity": "0.5", "average_cost": 100,
                 "current_price": 100, "current_value": 50, "unrealized_pnl": 0,
                 "previous_close": 100, "daily_pnl": 0, "realized_pnl": 1},
            ])
        elif self.path.startswith("/api/market/refresh"):
            payload = {"id": "refresh-1", "status": "completed", "succeeded": 1, "failed": 0, "results": []}
        elif self.path.startswith("/api/market/status"):
            payload = {"status": "ok", "assets": [], "fx": []}
        elif self.path.startswith("/api/market/exchange-rates"):
            payload = {"CNY": 1.0, "USD": 7.0}
        elif self.path.startswith("/api/portfolio/history"):
            payload = {
                "history": [
                    {
                        "date": "2026-07-23",
                        "total_value": 230,
                        "total_cost": 200,
                        "net_deposit": 200,
                        "return_rate": 0.15,
                    },
                    {
                        "date": "2026-07-24",
                        "total_value": 240,
                        "total_cost": 200,
                        "net_deposit": 200,
                        "return_rate": 0.2,
                    },
                ],
                "period": "1y",
                "data_status": "ok",
                "warnings": [],
                "data_as_of": "2026-07-24T10:00:00+00:00",
            }
        elif self.path.startswith("/api/accounts/"):
            payload = [
                {
                    "id": "account-1",
                    "name": "Test Account",
                    "currency": "CNY",
                }
            ]
        else:
            self.send_error(404)
            return

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class DashboardSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DashboardStubHandler)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()
        # The dashboard imports this singleton. Replace its transport client even
        # when another test already imported it with the developer's BACKEND_URL.
        stub_url = f"http://127.0.0.1:{cls.server.server_port}"
        http = httpx.Client(base_url=stub_url, trust_env=False)
        cls.addClassCleanup(http.close)
        replacement = patch.object(api, "_client", http)
        replacement.start()
        cls.addClassCleanup(replacement.stop)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_dashboard_renders_snapshot_data_without_exception(self):
        app = AppTest.from_file("app.py").run(timeout=10)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.title[0].value, "💹 Personal Finance Dashboard")
        self.assertTrue(any("590.00" in metric.value for metric in app.metric))

    def test_detail_filters_closed_and_sorts_by_converted_value(self):
        app = AppTest.from_file("app.py").run(timeout=10)

        def visible_symbols():
            self.assertEqual(list(app.exception), [])
            table = next(item.value for item in app.dataframe if "持仓数量" in item.value.columns)
            return table["代码"].tolist()

        toggle = next(item for item in app.toggle if item.label == "显示已清仓（1）")
        self.assertFalse(toggle.value)
        active_symbols = ["USDSTOCK", "TEST", "UNPRICED"]
        self.assertEqual(visible_symbols(), active_symbols)
        totals = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(totals["已实现总收益 (CNY)"], "21.00")

        toggle.set_value(True).run(timeout=10)
        self.assertEqual(visible_symbols(), active_symbols + ["CLOSED"])
        self.assertEqual({metric.label: metric.value for metric in app.metric}, totals)

    def test_refresh_button_requests_prices_and_shows_distinct_times(self):
        DashboardStubHandler.refresh_requests = 0
        app = AppTest.from_file("app.py").run(timeout=10)
        app.button[0].click().run(timeout=10)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(DashboardStubHandler.refresh_requests, 1)
        self.assertTrue(any("查询完成" in message.value for message in app.success))
        table = next(table.value for table in app.dataframe if "行情时间" in table.value.columns)
        row = table.set_index("代码").loc["TEST"]
        self.assertEqual(row["行情时间"], "2026-07-23")
        self.assertEqual(row["采集成功时间"], "2026-07-24 18:00:00")


if __name__ == "__main__":
    unittest.main()
