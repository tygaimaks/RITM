import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import database as db
from bot import bot
from config import TIMEZONE

log = logging.getLogger("rhythm.digest")


async def morning_digest() -> None:
    for stud in db.get_all_students():
        user = db.get_user(stud["id"])
        if not user:
            continue
        text = f"Доброе утро, {user['name']}! ☀️\n\n"

        if user["class_id"]:
            sched = db.get_schedule(user["class_id"])
            today = datetime.now(ZoneInfo(TIMEZONE)).weekday()
            today_lessons = [s for s in sched if s["day_of_week"] == today]
            if today_lessons:
                text += "📅 Уроки сегодня:\n"
                for l in today_lessons:
                    text += f"  {l['time']} — {l['subject']}\n"
            else:
                text += "📅 Сегодня уроков нет — можно отдохнуть.\n"

        pending = [t for t in db.get_tasks(user["id"]) if not t["is_done"]]
        if pending:
            text += "\n📝 Задачи на сегодня:\n"
            for t in pending[:5]:
                deadline_info = f" (до {t['deadline']})" if t['deadline'] else ""
                text += f"  • [{t['subject']}] {t['title']}{deadline_info}\n"
            if len(pending) > 5:
                text += f"  … и ещё {len(pending) - 5}\n"
            text += "\nОткрыть список: /menu → «Мои задачи»."
        else:
            text += "\n🎉 Незакрытых задач нет. Отличная работа!"

        if user["ovz"]:
            text += "\n\n🧩 Спокойный режим включён. Не торопитесь, всё успеете."

        try:
            await bot.send_message(chat_id=int(user["id"]), text=text)
        except Exception as e:
            log.warning("Не удалось отправить дайджест %s: %s", user["id"], e)


async def evening_reminder() -> None:
    for stud in db.get_all_students():
        user = db.get_user(stud["id"])
        if not user:
            continue
        pending = [t for t in db.get_tasks(user["id"]) if not t["is_done"]]
        if not pending:
            continue
        first = pending[0]
        deadline_info = f" (дедлайн: {first['deadline']})" if first['deadline'] else ""
        text = (
            f"{user['name']}, добрый вечер! 🌙\n\n"
            f"Осталось незакрытых задач: {len(pending)}.\n"
            f"Первая: [{first['subject']}] {first['title']}{deadline_info}\n\n"
            f"Если есть 10 минут — начните с неё. /menu → «Мои задачи»."
        )
        try:
            await bot.send_message(chat_id=int(user["id"]), text=text)
        except Exception as e:
            log.warning("Не удалось отправить напоминание %s: %s", user["id"], e)