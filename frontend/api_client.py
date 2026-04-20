import os
import httpx
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

# We will use st.secrets if deployed, otherwise fallback to locally loaded env variables
# If Streamlit is running locally, it can read from .env.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

# 统一超时配置：连接超时 5s，读取超时 30s（持仓计算等接口可能稍慢）
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

# 传输层配置：允许连接池保留 10 个长连接，避免重复 TCP 握手导致的超时
_TRANSPORT = httpx.HTTPTransport(
    retries=2,               # 网络抖动时自动重试 2 次（幂等请求）
    limits=httpx.Limits(
        max_connections=10,
        max_keepalive_connections=5,
        keepalive_expiry=20,  # 主动在 20s 内复用连接，不等系统超时断开
    ),
)

class FinanceAPIClient:
    def __init__(self, base_url: str = BACKEND_URL):
        self.base_url = base_url.rstrip("/")
        # 单例持久化 Client：整个 Streamlit 进程共享同一个连接池
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=_TIMEOUT,
            transport=_TRANSPORT,
        )

    def _request(self, method: str, path: str, **kwargs) -> Any:
        """带自动重连的通用请求方法。
        当连接因为长时间空闲而断开时，httpx 的 retries 机制会自动重建连接。
        """
        try:
            response = self._client.request(method, path, **kwargs)
        except (httpx.RemoteProtocolError, httpx.ConnectError):
            # 服务端主动关闭了空闲连接（keep-alive 超时），手动重新发送一次
            response = self._client.request(method, path, **kwargs)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise Exception(f"API Error ({e.response.status_code}): {e.response.text}")
        return response.json()

    def _request_no_body(self, method: str, path: str, **kwargs) -> None:
        """用于 DELETE 等不需要解析响应体的请求。"""
        try:
            response = self._client.request(method, path, **kwargs)
        except (httpx.RemoteProtocolError, httpx.ConnectError):
            response = self._client.request(method, path, **kwargs)
        response.raise_for_status()

    # ── Accounts ──────────────────────────────────────────────────────────
    def get_accounts(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/accounts/")

    def create_account(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/accounts/", json=data)

    def delete_account(self, account_id: str) -> None:
        self._request_no_body("DELETE", f"/api/accounts/{account_id}")

    # ── Assets ────────────────────────────────────────────────────────────
    def get_assets(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/assets/")

    def create_asset(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/assets/", json=data)

    def delete_asset(self, asset_id: str) -> None:
        self._request_no_body("DELETE", f"/api/assets/{asset_id}")

    def create_custom_asset_price(self, asset_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"/api/assets/{asset_id}/prices", json=data)

    def get_custom_asset_prices(self, asset_id: str) -> List[Dict[str, Any]]:
        return self._request("GET", f"/api/assets/{asset_id}/prices")

    # ── Transactions ───────────────────────────────────────────────────────
    def get_transactions(self, account_id: Optional[str] = None, asset_id: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {}
        if account_id: params["account_id"] = account_id
        if asset_id: params["asset_id"] = asset_id
        return self._request("GET", "/api/transactions/", params=params)

    def create_transaction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/transactions/", json=data)

    def delete_transaction(self, tx_id: str) -> None:
        self._request_no_body("DELETE", f"/api/transactions/{tx_id}")

    # ── Positions ─────────────────────────────────────────────────────────
    def get_positions(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/positions/")

    # ── Alert Rules ───────────────────────────────────────────────────────
    def get_alert_rules(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/api/alert_rules/")

    def create_alert_rule(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/alert_rules/", json=data)

    def update_alert_rule(self, rule_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PATCH", f"/api/alert_rules/{rule_id}", json=data)

    def delete_alert_rule(self, rule_id: str) -> None:
        self._request_no_body("DELETE", f"/api/alert_rules/{rule_id}")

    # ── Portfolio ─────────────────────────────────────────────────────────
    def get_portfolio_history(self, period: str = "1y", account_id: Optional[str] = None, base_currency: str = "CNY") -> Dict[str, Any]:
        params = {"period": period, "base_currency": base_currency}
        if account_id: params["account_id"] = account_id
        return self._request("GET", "/api/portfolio/history", params=params)

    # ── Market ────────────────────────────────────────────────────────────
    def get_exchange_rates(self, base: str, targets: List[str]) -> Dict[str, float]:
        if not targets:
            return {}
        return self._request("GET", "/api/market/exchange-rates", params={"base": base, "targets": targets})


api = FinanceAPIClient()
