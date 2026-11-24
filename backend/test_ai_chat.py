import json
import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.routers import ai
from src.schemas.positions import PositionResponse
from src.services.ai_portfolio import portfolio_summary, summarize


def position(**changes):
    data = dict(account_id="private-account", asset_id="private-instrument", symbol="AAA",
                name="private asset name", asset_type="ETF", currency="USD",
                total_quantity=1, average_cost=123456, current_value=Decimal("100"),
                price_status="ok", price_market_time="2026-11-19", price_source="tencent",
                price_error="private provider error with account info")
    return PositionResponse(**{**data, **changes})


class SummaryTests(unittest.TestCase):
    def test_cross_account_weighting_fx_coverage_and_privacy(self):
        positions = [
            position(), position(account_id="private-second-account", current_value=50),
            position(symbol="private-Custom-symbol", asset_id="private-custom-id", asset_type="Custom",
                     currency="CNY", current_value=350, price_source="manual"),
            position(symbol="NOQUOTE", current_value=None, price_market_time=None),
            position(symbol="NOFX", currency="GBP"),
            position(symbol="CLOSED", total_quantity=0),
        ]
        with patch("src.services.positions.calculate_positions", return_value=positions), patch(
            "src.services.market_store.get_cached_exchange_rates",
            return_value=({"CNY": 1, "USD": 7}, {"USD": {"as_of": "2020-01-01", "status": "ok"}}, None),
        ):
            summary = portfolio_summary()
        self.assertEqual(summary["open_position_rows"], 5)
        self.assertEqual(summary["unvalued_position_rows"], 2)
        self.assertEqual(summary["by_currency_pct"], {"CNY": 25, "USD": 75})
        self.assertEqual(summary["by_asset_type_pct"], {"ETF": 75, "Custom": 25})
        self.assertEqual(summary["largest_three_weight_pct"], 100)
        holdings = {h["symbol"]: h for h in summary["holdings"]}
        self.assertEqual(holdings["AAA"]["weight_pct"], 75)
        self.assertIsNone(holdings["NOQUOTE"]["weight_pct"])
        self.assertIn("缺少有效汇率", holdings["NOFX"]["warnings"])
        self.assertEqual({r["status"] for r in summary["fx"]}, {"旧汇率或不可用"})
        wire = json.dumps(summary)
        for private in ("private", "account_id", "asset_id", "total_quantity", "current_price",
                        "current_value", "123456", "CLOSED", "trade_time", "price_error"):
            self.assertNotIn(private, wire)

    def test_no_valued_assets_no_divide_by_zero_and_distinct_custom_assets(self):
        positions = [position(asset_type="Custom", current_value=None, asset_id=key)
                     for key in ("id1", "id2")]
        summary = summarize(positions, {}, {}, date.today())
        self.assertEqual(len({h["symbol"] for h in summary["holdings"]}), 2)
        self.assertTrue(all(h["weight_pct"] is None for h in summary["holdings"]))
        self.assertIsNone(summary["largest_three_weight_pct"])
        self.assertEqual(summarize([], {}, {}, date.today())["holdings"], [])

    def test_top_three_uses_unrounded_values_and_dates_per_instrument(self):
        positions = [position(symbol=symbol, current_value=value, price_market_time=day)
                     for symbol, value, day in [("A", 4, "2026-11-01"), ("B", 3, "2026-11-19"),
                                                ("C", 2, None), ("D", 1, "2026-11-19")]]
        summary = summarize(positions, {"USD": 7}, {}, date(2026, 11, 20))
        self.assertEqual(summary["largest_three_weight_pct"], 90)
        self.assertEqual(summary["holdings"][0]["warnings"], ["使用旧报价"])
        self.assertIn("行情日期未知", summary["holdings"][2]["warnings"])


class ChatTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(ai.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer chat-secret"}
        self.data = {"provider": "api", "messages": [{"role": "user", "content": "测试问题"}]}
        env = {"AI_CHAT_ACCESS_TOKEN": "chat-secret", "AI_API_KEY": "api-secret",
               "AI_API_BASE_URL": "https://example.invalid/v1/", "AI_API_MODEL": "model",
               "FINANCE_BOARD_BRIDGE_TOKEN": "bridge-secret"}
        self.enter_patch(patch.dict(os.environ, env, clear=True))

    def enter_patch(self, target):
        value = target.start()
        self.addCleanup(target.stop)
        return value

    def test_disabled_configuration_and_wrong_token_do_not_read_holdings(self):
        with patch.object(ai, "portfolio_summary") as summary:
            self.assertEqual(self.client.post("/api/ai/chat", json=self.data).status_code, 401)
            with patch.dict(os.environ, {"AI_CHAT_ACCESS_TOKEN": ""}):
                status = self.client.get("/api/ai/status").json()
                self.assertFalse(status["access_configured"])
                self.assertFalse(any(p["configured"] for p in status["providers"]))
                self.assertEqual(self.client.post("/api/ai/chat", json=self.data, headers=self.headers).status_code, 503)
            with patch.dict(os.environ, {"AI_API_BASE_URL": "http://external.invalid/v1"}):
                response = self.client.post("/api/ai/chat", json=self.data, headers=self.headers)
                self.assertEqual(response.status_code, 503)
        summary.assert_not_called()
        self.assertNotIn("secret", self.client.get("/api/ai/status").text)

    def test_invalid_transcript_or_client_selecting_endpoint_rejected(self):
        invalid = [
            {**self.data, "messages": [{"role": "system", "content": "bad"}]},
            {**self.data, "base_url": "https://elsewhere.invalid"},
            {**self.data, "messages": self.data["messages"] * 3},
            {**self.data, "messages": [{"role": "user", "content": "x" * 4001}]},
        ]
        with patch.object(ai, "portfolio_summary") as summary:
            for body in invalid:
                self.assertEqual(self.client.post("/api/ai/chat", json=body, headers=self.headers).status_code, 422)
        summary.assert_not_called()

    def call_with_mock(self, provider, status, payload):
        data = {**self.data, "provider": provider}
        request = httpx.Request("POST", "https://example.invalid")
        with patch.object(ai, "portfolio_summary", return_value={"holdings": []}), patch.object(
            ai.httpx.Client, "post", autospec=True,
            return_value=httpx.Response(status, json=payload, request=request),
        ) as post:
            # TestClient.post itself uses httpx.Client.post. Use request() to exercise ASGI normally.
            response = self.client.request("POST", "/api/ai/chat", json=data, headers=self.headers)
        return response, post.call_args

    def test_api_uses_only_backend_chosen_model_key_and_snapshot(self):
        response, call = self.call_with_mock("api", 200, {"choices": [{"message": {"content": "answer"}}]})
        self.assertEqual(response.json(), {"reply": "answer"})
        self.assertEqual(call.args[1], "https://example.invalid/v1/chat/completions")
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bearer api-secret")
        body = call.kwargs["json"]
        self.assertEqual(body["model"], "model")
        self.assertEqual(json.loads(body["messages"][-1]["content"]),
                         {"portfolio": {"holdings": []}, "question": "测试问题"})
        self.assertNotIn("secret", json.dumps(body))

    def test_bridge_contract_and_distinct_credential(self):
        response, call = self.call_with_mock("codex", 200, {"reply": "answer"})
        self.assertEqual(response.json(), {"reply": "answer"})
        self.assertEqual(call.args[1], "http://host.docker.internal:8765/chat")
        self.assertEqual(call.kwargs["headers"], {"Authorization": "Bearer bridge-secret"})
        self.assertEqual(call.kwargs["json"], {"portfolio": {"holdings": []}, "messages": self.data["messages"]})

    def test_provider_failure_no_replay_or_sensitive_details(self):
        for status, expected in [(429, 429), (403, 502), (500, 502), (504, 504)]:
            response, _ = self.call_with_mock("codex", status, {"error": "private details"})
            self.assertEqual(response.status_code, expected)
            self.assertNotIn("private details", response.text)
        response, _ = self.call_with_mock("api", 200, {"choices": []})
        self.assertEqual(response.status_code, 502)
        response, _ = self.call_with_mock("codex", 200, {"reply": "a" * 13000})
        self.assertEqual(len(response.json()["reply"]), 12000)

    def test_database_failure_releases_slot_and_never_calls_provider(self):
        with patch.object(ai, "portfolio_summary", side_effect=ValueError("private URL")), patch.object(ai, "provider_reply") as provider:
            for _ in range(2):
                response = self.client.post("/api/ai/chat", json=self.data, headers=self.headers)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("private URL", response.text)
            provider.assert_not_called()

    def test_concurrent_send_returns_busy_before_loading_snapshot(self):
        with ai.active_chat, patch.object(ai, "portfolio_summary") as summary:
            response = self.client.post("/api/ai/chat", json=self.data, headers=self.headers)
            self.assertEqual(response.status_code, 429)
            summary.assert_not_called()


if __name__ == "__main__":
    unittest.main()
