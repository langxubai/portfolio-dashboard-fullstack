import os
import httpx
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

# We will use st.secrets if deployed, otherwise fallback to locally loaded env variables
# If Streamlit is running locally, it can read from .env.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

class FinanceAPIClient:
    def __init__(self, base_url: str = BACKEND_URL):
        self.base_url = base_url.rstrip("/")
        
    def _handle_response(self, response: httpx.Response) -> Any:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise Exception(f"API Error ({e.response.status_code}): {e.response.text}")
        return response.json()
        
    def get_accounts(self) -> List[Dict[str, Any]]:
        with httpx.Client() as client:
            resp = client.get(f"{self.base_url}/api/accounts/")
            return self._handle_response(resp)
            
    def create_account(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client() as client:
            resp = client.post(f"{self.base_url}/api/accounts/", json=data)
            return self._handle_response(resp)

    def get_assets(self) -> List[Dict[str, Any]]:
        with httpx.Client() as client:
            resp = client.get(f"{self.base_url}/api/assets/")
            return self._handle_response(resp)
            
    def create_asset(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client() as client:
            resp = client.post(f"{self.base_url}/api/assets/", json=data)
            return self._handle_response(resp)

    def get_transactions(self, account_id: Optional[str] = None, asset_id: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {}
        if account_id: params["account_id"] = account_id
        if asset_id: params["asset_id"] = asset_id
        with httpx.Client() as client:
            resp = client.get(f"{self.base_url}/api/transactions/", params=params)
            return self._handle_response(resp)
            
    def create_transaction(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client() as client:
            resp = client.post(f"{self.base_url}/api/transactions/", json=data)
            return self._handle_response(resp)
            
    def get_positions(self) -> List[Dict[str, Any]]:
        with httpx.Client() as client:
            resp = client.get(f"{self.base_url}/api/positions/")
            return self._handle_response(resp)
            
    def get_alert_rules(self) -> List[Dict[str, Any]]:
        with httpx.Client() as client:
            resp = client.get(f"{self.base_url}/api/alert_rules/")
            return self._handle_response(resp)
            
    def create_alert_rule(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client() as client:
            resp = client.post(f"{self.base_url}/api/alert_rules/", json=data)
            return self._handle_response(resp)

    def update_alert_rule(self, rule_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        with httpx.Client() as client:
            resp = client.patch(f"{self.base_url}/api/alert_rules/{rule_id}", json=data)
            return self._handle_response(resp)

    def delete_alert_rule(self, rule_id: str) -> None:
        with httpx.Client() as client:
            resp = client.delete(f"{self.base_url}/api/alert_rules/{rule_id}")
            resp.raise_for_status()

api = FinanceAPIClient()
