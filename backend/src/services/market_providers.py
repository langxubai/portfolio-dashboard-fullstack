"""Quote adapters. Each call runs in a disposable process with a hard deadline."""

from datetime import datetime, timezone
import math
import re
from zoneinfo import ZoneInfo

import httpx


def tencent_code(asset):
    symbol = asset["symbol"].upper()
    if asset["asset_type"] not in {"Stock", "ETF", "Fund"}:
        return None
    if asset["currency"] == "USD" and re.fullmatch(r"[A-Z]{1,8}", symbol):
        return "us" + symbol
    if asset["currency"] == "HKD" and re.fullmatch(r"\d{1,5}\.HK", symbol):
        return "hk" + symbol[:-3].zfill(5)
    if asset["currency"] == "CNY":
        match = re.fullmatch(r"(\d{6})\.(SS|SZ)", symbol)
        if match:
            return ("sh" if match[2] == "SS" else "sz") + match[1]
    return None


def parse_tencent(text, assets):
    records = dict(re.findall(r'v_(\w+)="([^"]*)";', text))
    quotes = {}
    for asset in assets:
        code = tencent_code(asset)
        parts = records.get(code, "").split("~")
        if len(parts) < 36:
            continue
        try:
            expected = code[2:]
            returned = parts[2].split(".")[0]
            if returned != expected:
                continue
            if code.startswith("us") and parts[35] != "USD":
                continue
            zone = "America/New_York" if code.startswith("us") else "Asia/Shanghai"
            stamp = parts[30].replace("/", "-")
            if stamp.isdigit():
                at = datetime.strptime(stamp, "%Y%m%d%H%M%S")
            else:
                at = datetime.fromisoformat(stamp)
            at = at.replace(tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
            price, previous = float(parts[3]), float(parts[4])
            if not math.isfinite(price) or price <= 0:
                continue
            quotes[asset["symbol"]] = {
                "current_price": price,
                "previous_close": previous if math.isfinite(previous) and previous > 0 else None,
                "as_of": at.isoformat(),
                "kind": "quote",
                "source": "tencent",
            }
        except (ValueError, IndexError):
            continue
    return quotes


def tencent_quotes(assets):
    codes = sorted({code for a in assets if (code := tencent_code(a))})
    if not codes:
        return {}
    response = httpx.get("https://qt.gtimg.cn/", params={"q": ",".join(codes)}, timeout=6)
    response.raise_for_status()
    return parse_tencent(response.content.decode("gb18030"), assets)


def coinbase_quote(asset):
    symbol = asset["symbol"].upper()
    if not re.fullmatch(r"[A-Z0-9]{2,12}-USD", symbol) or asset["currency"] != "USD":
        return {}
    response = httpx.get(f"https://api.exchange.coinbase.com/products/{symbol}/ticker", timeout=6)
    response.raise_for_status()
    data = response.json()
    at = datetime.fromisoformat(data["time"].replace("Z", "+00:00"))
    return {asset["symbol"]: {
        "current_price": float(data["price"]),
        "previous_close": None,
        "as_of": at.isoformat(),
        "kind": "quote",
        "source": "coinbase",
    }}


def reference_fx(currencies):
    response = httpx.get("https://api.frankfurter.dev/v1/latest", params={
        "base": "USD", "symbols": ",".join(c for c in currencies if c != "USD"),
    }, timeout=6)
    response.raise_for_status()
    data = response.json()
    if data["base"] != "USD":
        raise ValueError("Unexpected FX base currency")
    rates = {"USD": 1.0, **data["rates"]}
    return {f"{target}/{base}": {
        "current_price": float(rates[base]) / float(rates[target]),
        "as_of": data["date"], "kind": "reference_rate", "source": "frankfurter",
    } for target in currencies for base in currencies
        if target != base and target in rates and base in rates}


def run(provider, payload):
    if provider == "tencent":
        return tencent_quotes(payload)
    if provider == "coinbase":
        return coinbase_quote(payload)
    if provider == "frankfurter":
        return reference_fx(payload)

    # Load native dependencies only inside workers that need them.
    from src.services import market_data
    if provider == "yahoo":
        quotes, error = market_data.fetch_yfinance_quotes(payload)
        if not quotes:
            raise ValueError(error)
        return quotes
    if provider == "fund":
        quote = market_data.fetch_fund_cn_price(payload)
        return {payload: quote} if quote else {}
    if provider in {"yahoo_history", "fund_history"}:
        download = (market_data.download_historical_prices if provider == "yahoo_history"
                    else market_data.download_fund_cn_historical_prices)
        frame = download(payload["symbols"], period=payload["period"])
        return {symbol: {str(index.date()): float(value)
                         for index, value in frame[symbol].dropna().items()}
                for symbol in frame.columns}
    raise ValueError("Unknown provider")
