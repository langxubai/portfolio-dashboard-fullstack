"""Bound total provider time, including DNS, authentication, retries and threads."""

import json
from pathlib import Path
import subprocess
import sys


def call_provider(provider, payload, timeout=15):
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "src.services.market_worker"],
            input=json.dumps({"provider": provider, "payload": payload}),
            text=True, capture_output=True, timeout=timeout,
            cwd=Path(__file__).resolve().parents[2],
        )
    except subprocess.TimeoutExpired:
        return {}, f"{provider} 超过 {timeout} 秒，已结束本次请求"
    except OSError as exc:
        return {}, f"{provider} 无法启动 ({type(exc).__name__})"
    for line in reversed(result.stdout.splitlines()):
        if line.startswith("MARKET_RESULT="):
            try:
                response = json.loads(line.removeprefix("MARKET_RESULT="))
                return response["data"], response["error"]
            except (ValueError, KeyError):
                break
    return {}, f"{provider} 未返回有效结果"
