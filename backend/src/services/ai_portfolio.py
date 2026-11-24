"""Build the only portfolio data that can leave the backend for a chat turn."""

import re
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

BASE = "CNY"
TYPES = {"Stock", "ETF", "Fund", "FundCN", "Crypto", "Forex"}
SOURCES = {"tencent", "coinbase", "yfinance", "akshare", "manual", "frankfurter"}


def market_day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def percentage(value, total):
    return float(round(value * 100 / total, 2)) if total > 0 else None


def portfolio_summary():
    from src.services.market_store import get_cached_exchange_rates
    from src.services.positions import calculate_positions

    positions = [p for p in calculate_positions() if p.total_quantity > 0]
    rates, snapshots, _ = get_cached_exchange_rates(BASE, {p.currency for p in positions})
    return summarize(positions, rates, snapshots, datetime.now(timezone.utc).date())


def summarize(positions, rates, snapshots, today):
    # The same instrument can occur in several accounts. Custom assets may have
    # identical symbols yet represent distinct instruments. Their IDs stay local.
    aliases = {}
    groups = {}
    currency_values = defaultdict(Decimal)
    class_values = defaultdict(Decimal)
    valued_rows = 0
    for p in sorted(positions, key=lambda p: p.asset_id):
        currency = p.currency.upper()
        public_currency = currency if re.fullmatch(r"[A-Z]{3}", currency) else "未知"
        asset_type = p.asset_type if p.asset_type in TYPES else "Custom"
        symbol = p.symbol.upper()
        if asset_type == "Custom" or not re.fullmatch(r"[A-Z0-9^][A-Z0-9._=^/-]{0,24}", symbol):
            symbol = aliases.setdefault(p.asset_id, f"匿名资产 {len(aliases) + 1}")
        key = (symbol, asset_type, public_currency)
        if key not in groups:
            groups[key] = {"value": Decimal(0), "valued": False, "warnings": set(),
                           "dates": set(), "sources": set()}
        group = groups[key]
        quote_day = market_day(p.price_market_time)
        if quote_day:
            group["dates"].add(quote_day.isoformat())
        if p.price_source in SOURCES:
            group["sources"].add(p.price_source)

        rate = rates.get(currency)
        if p.current_value is None:
            group["warnings"].add("缺少报价")
        if rate is None or not Decimal(str(rate)).is_finite() or rate <= 0:
            group["warnings"].add("缺少有效汇率")
            continue
        if p.current_value is None:
            continue
        if p.price_is_stale or p.price_status != "ok" or (quote_day and (today - quote_day).days > 5):
            group["warnings"].add("使用旧报价")
        if quote_day is None:
            group["warnings"].add("行情日期未知")
        value = p.current_value * Decimal(str(rate))
        group["value"] += value
        group["valued"] = True
        valued_rows += 1
        currency_values[public_currency] += value
        class_values[asset_type] += value

    total = sum(currency_values.values(), Decimal(0))
    ranked = sorted(groups.items(), key=lambda pair: (-pair[1]["value"], pair[0]))
    holdings = []
    for (symbol, asset_type, currency), group in ranked:
        holdings.append({
            "symbol": symbol, "asset_type": asset_type, "quotation_currency": currency,
            "weight_pct": percentage(group["value"], total) if group["valued"] else None,
            "oldest_quote_date": min(group["dates"], default=None),
            "quote_sources": sorted(group["sources"]), "warnings": sorted(group["warnings"]),
        })
    fx = []
    for currency in sorted({p.currency.upper() for p in positions} - {BASE}):
        snapshot = snapshots.get(currency, {})
        as_of = market_day(snapshot.get("as_of"))
        status = "日期未知" if as_of is None else "ok"
        if snapshot.get("status") != "ok" or (as_of and (today - as_of).days > 5):
            status = "旧汇率或不可用"
        fx.append({"currency": currency if re.fullmatch(r"[A-Z]{3}", currency) else "未知",
                   "as_of": as_of.isoformat() if as_of else None, "status": status})
    return {
        "summary_date_utc": today.isoformat(), "base_currency": BASE,
        "scope": "跨账户的当前持仓，可估值部分折算人民币后为分母。不含账户现金余额及已平仓项目。币种指计价币种。",
        "open_position_rows": len(positions), "unvalued_position_rows": len(positions) - valued_rows,
        "holdings": holdings, "fx": fx,
        "by_currency_pct": {k: percentage(v, total) for k, v in sorted(currency_values.items())},
        "by_asset_type_pct": {k: percentage(v, total) for k, v in sorted(class_values.items())},
        "largest_three_weight_pct": percentage(sum(g["value"] for _, g in ranked[:3]), total),
    }
