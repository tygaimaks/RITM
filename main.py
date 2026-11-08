import asyncio
import logging

from apscheduler.triggers.cron import CronTrigger

import database as db
from bot import bot, dp, scheduler
from config import TIMEZONE
import handlers
import messages
from scheduler_jobs import evening_reminder, morning_digest

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s"
)
log = logging.getLogger("rhythm.main")


async def main() -> None:
    db.init_db()

    handlers.register(dp)
    messages.register(dp)

    scheduler.add_job(
        morning_digest,
        CronTrigger(hour=11, minute=56, timezone=TIMEZONE),
        id="morning_digest",
        replace_existing=True,
    )
    scheduler.add_job(
        evening_reminder,
        CronTrigger(hour=19, minute=0, timezone=TIMEZONE),
        id="evening_reminder",
        replace_existing=True,
    )
    scheduler.start()
    log.info("Дайджесты запланированы (TZ=%s): 07:30 и 19:00", TIMEZONE)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())