import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from streamlit.testing.v1 import AppTest


class DashboardStubHandler(BaseHTTPRequestHandler):
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
                    "total_quantity": 2,
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
                    "price_is_stale": False,
                    "price_error": None,
                }
            ]
        elif self.path.startswith("/api/market/exchange-rates"):
            payload = {"CNY": 1.0}
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
        os.environ["BACKEND_URL"] = (
            f"http://127.0.0.1:{cls.server.server_address[1]}"
        )

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_dashboard_renders_snapshot_data_without_exception(self):
        app = AppTest.from_file("app.py").run(timeout=10)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.title[0].value, "💹 Personal Finance Dashboard")
        self.assertTrue(any("240.00" in metric.value for metric in app.metric))


if __name__ == "__main__":
    unittest.main()
