import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from src.services.alert_engine import evaluate_all_rules

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

def start_scheduler():
    if not scheduler.running:
        setup_scheduler()
        scheduler.start()
        logger.info("Scheduler started successfully.")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown.")
