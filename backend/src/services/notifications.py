import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

BARK_URL = os.getenv("BARK_URL")

async def send_bark_notification(title: str, body: str) -> bool:
    """
    Sends a push notification via Bark.
    """
    if not BARK_URL:
        logger.warning("BARK_URL is not configured. Skipping notification.")
        return False
    
    # Ensure URL ends with slash for correct path joining
    base_url = BARK_URL if BARK_URL.endswith('/') else f"{BARK_URL}/"
    
    # Bark endpoint format: http://api.day.app/yourkey/title/body
    url = f"{base_url}{title}/{body}"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            logger.info(f"Bark notification sent successfully: {title}")
            return True
    except Exception as e:
        logger.error(f"Failed to send Bark notification: {e}")
        return False

async def send_alert(asset_symbol: str, rule_type: str, message: str) -> bool:
    """
    Abstract layer for sending alerts. Dispatches to configured channels.
    """
    title = f"Alert [{asset_symbol}] - {rule_type}"
    return await send_bark_notification(title, message)
