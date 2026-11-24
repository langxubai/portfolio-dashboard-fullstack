import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from src.services.alert_engine import evaluate_all_rules
from src.services.market_collector import refresh_market_history
from src.services.market_refresh import request_market_refresh

logger = logging.getLogger(__name__)

# Initialize the Async scheduler
scheduler = AsyncIOScheduler()

def setup_scheduler():
    logger.info("Setting up APScheduler...")
    scheduler.add_job(
        evaluate_all_rules,
        trigger=IntervalTrigger(minutes=5),
        id="evaluate_alerts_job",
        name="Evaluate active alert rules every 5 minutes",
        replace_existing=True,
    )
    scheduler.add_job(
        request_market_refresh,
        trigger=IntervalTrigger(minutes=5),
        id="refresh_market_quotes_job",
        name="Refresh persisted market quotes every 5 minutes",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=2),
    )
    scheduler.add_job(
        refresh_market_history,
        trigger=IntervalTrigger(hours=1),
        id="refresh_market_history_job",
        name="Refresh persisted daily market history every hour",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=15),
    )

def start_scheduler():
    if not scheduler.running:
        setup_scheduler()
        scheduler.start()
        logger.info("Scheduler started successfully.")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown.")
