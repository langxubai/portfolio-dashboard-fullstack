import sys
import os
# Enable importing src module from backend dir
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging
from src.services.alert_engine import evaluate_all_rules

logging.basicConfig(level=logging.INFO)

async def test():
    await evaluate_all_rules()

if __name__ == "__main__":
    asyncio.run(test())
