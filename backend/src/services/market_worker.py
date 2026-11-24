"""A worker never writes to the database, including after a caller times out."""

import json
import sys

from src.services.market_providers import run


if __name__ == "__main__":
    request = json.load(sys.stdin)
    try:
        result = {"data": run(request["provider"], request["payload"]), "error": None}
        encoded = json.dumps(result, allow_nan=False)
    except Exception as exc:
        encoded = json.dumps({"data": {}, "error": f"{request['provider']} 请求失败 ({type(exc).__name__})"})
    print("MARKET_RESULT=" + encoded)
