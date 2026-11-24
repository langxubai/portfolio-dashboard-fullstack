"""Send one fictional portfolio question through a configured model provider."""

import argparse
import re
import sys
import unicodedata

from fastapi import HTTPException

from src.routers.ai import provider_configured, provider_reply


def check(provider):
    if not provider_configured(provider):
        print("未运行：所选模型通道配置不完整。", file=sys.stderr)
        return 2
    # The provider adapter receives constants. Do not call portfolio_summary() or
    # import the live application, its scheduler, or the database client here.
    portfolio = {
        "scope": "虚构测试组合，仅含两只人民币计价的已估值资产，无现金或缺价。",
        "base_currency": "CNY", "open_position_rows": 2, "unvalued_position_rows": 0,
        "holdings": [
            {"symbol": "DEMO-A", "weight_pct": 60},
            {"symbol": "DEMO-B", "weight_pct": 40},
        ],
    }
    question = "这个虚构组合中最大单个仓位占已估值持仓的百分之几？请只输出该百分比。"
    print(f"正在用虚构仓位检查 {provider} 通道……", flush=True)
    try:
        reply = provider_reply(provider, [{"role": "user", "content": question}], portfolio)
    except HTTPException as exc:
        # provider_reply maps upstream errors to sanitized messages. Keep this
        # operator command independent of any future additions to their text.
        print(f"验证失败：模型通道返回 HTTP {exc.status_code}。", file=sys.stderr)
        return 1
    except Exception:
        print("验证失败：无法完成模型请求，请检查服务配置。", file=sys.stderr)
        return 1
    normalized = unicodedata.normalize("NFKC", reply).strip()
    if not re.fullmatch(r"60(?:\.0+)?\s*%?", normalized):
        print("收到回复，但内容不符合预期的单个百分比。", file=sys.stderr)
        return 1
    print("验证通过：模型从虚构持仓中读出了 60%。")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=["codex", "api"])
    sys.exit(check(parser.parse_args().provider))
