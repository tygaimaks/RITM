import logging

from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

import database as db
import texts as T
from bot import (
    DAYS,
    bot,
    class_link,
    format_schedule,
    get_menu,
    new_id,
)
from config import MAIN_ADMIN_ID
from states import clear_state, set_state

log = logging.getLogger("rhythm.handlers")


def _extract_start_payload(event) -> str | None:
    for attr in ("payload", "start_payload", "startPayload"):
        val = getattr(event, attr, None)
        if val:
            return str(val)
    data = getattr(event, "data", None)
    if isinstance(data, dict):
        for key in ("payload", "start_payload"):
            if data.get(key):
                return str(data[key])
    return None


def register(dp) -> None:

    @dp.bot_started()
    async def on_bot_started(event):
        _, user_id = event.get_ids()
        user_id = str(user_id)
        payload = _extract_start_payload(event)
        log.info("bot_started user=%s payload=%r", user_id, payload)
        if payload:
            db.save_pending_start(user_id, payload)

    @dp.message_callback()
    async def on_click(event):
        _, user_id = event.get_ids()
        user_id = str(user_id)
        payload = event.callback.payload or ""
        user = db.get_user(user_id)

        if not user:
            await event.send(T.NEED_START)
            return

        if payload == "menu":
            clear_state(user_id)
            await event.send(T.MENU, attachments=[get_menu(user)])
            return
        if payload == "help":
            await event.send(T.HELP)
            return

        if payload == "set_student":
            db.update_user(user_id, "role", "student")
            updated = db.get_user(user_id)
            await event.send(T.ROLE_STUDENT_OK, attachments=[get_menu(updated)])
            return
        if payload == "set_parent":
            db.update_user(user_id, "role", "parent")
            updated = db.get_user(user_id)
            await event.send(T.ROLE_PARENT_OK, attachments=[get_menu(updated)])
            return

        if payload == "admin_dir":
            if user_id != MAIN_ADMIN_ID:
                await event.send(T.NOT_FOR_ROLE)
                return
            set_state(user_id, {"action": "wait_dir"})
            await event.send(T.ADMIN_ASK_DIRECTOR)
            return

        if payload.startswith("admin_classes"):
            if user["role"] not in ["director", "zavuch"]:
                await event.send(T.NOT_FOR_ROLE)
                return
                
            page = 0
            if "_" in payload:
                page = int(payload.split("_")[2])
                
            classes = db.get_classes_of_school(user["school_id"])
            if not classes:
                await event.send("В школе пока нет классов. Загрузите расписание или создайте класс.")
                return
                
            per_page = 8
            start_idx = page * per_page
            end_idx = start_idx + per_page
            page_classes = classes[start_idx:end_idx]
            
            b = InlineKeyboardBuilder()
            for c in page_classes:
                teacher_id = db.get_teacher_of_class(c["id"])
                status = "✅" if teacher_id else "❌"
                b.row(CallbackButton(text=f"{status} {c['name']}", payload=f"manage_class_{c['id']}"))
            
            nav_row = []
            if page > 0:
                nav_row.append(CallbackButton(text="⬅️ Назад", payload=f"admin_classes_{page-1}"))
            if end_idx < len(classes):
                nav_row.append(CallbackButton(text="Вперед ➡️", payload=f"admin_classes_{page+1}"))
            
            if nav_row:
                b.row(*nav_row)
                
            b.row(CallbackButton(text="🔙 Главное меню", payload="menu"))
            
            await event.send(
                f"Выберите класс (Страница {page+1}):\n✅ — учитель назначен\n❌ — учителя нет", 
                attachments=[b.as_markup()]
            )
            return

        if payload.startswith("manage_class_"):
            if user["role"] not in ["director", "zavuch"]:
                await event.send(T.NOT_FOR_ROLE)
                return
                
            class_id = payload.split("_")[2]
            cls = db.get_class_by_id(class_id)
            if not cls:
                await event.send("Класс не найден.")
                return
                
            teacher_id = db.get_teacher_of_class(class_id)
            b = InlineKeyboardBuilder()
            
            if teacher_id:
                teacher = db.get_user(teacher_id)
                t_name = teacher["name"] if teacher else "Неизвестный"
                text = f"Класс «{cls['name']}»\nУчитель: {t_name}\n\nЧто хотите сделать?"
                b.row(CallbackButton(text="🔄 Сменить учителя", payload=f"change_teacher_{class_id}"))
                b.row(CallbackButton(text="❌ Отвязать учителя", payload=f"unlink_teacher_{class_id}"))
            else:
                text = f"Класс «{cls['name']}»\nУчитель: не назначен\n\nНазначьте учителя для этого класса."
                b.row(CallbackButton(text="👨‍🏫 Назначить учителя", payload=f"change_teacher_{class_id}"))
                
            b.row(CallbackButton(text="🔙 К списку классов", payload="admin_classes_0"))
            await event.send(text, attachments=[b.as_markup()])
            return

        if payload.startswith("unlink_teacher_"):
            class_id = payload.split("_")[2]
            teacher_id = db.get_teacher_of_class(class_id)
            if teacher_id:
                db.update_user(teacher_id, "class_id", None)
                db.remove_teacher_memberships(teacher_id)
                await event.send("Учитель отвязан от класса.")
            await event.send("Возврат к списку:", attachments=[get_menu(user)])
            return

        if payload.startswith("change_teacher_"):
            class_id = payload.split("_")[2]
            set_state(user_id, {"action": "wait_teacher_id_for_class", "class_id": class_id})
            await event.send(T.ADMIN_ASK_TEACHER_ID_FOR_CLASS)
            return

        if payload == "dir_school":
            if user["role"] != "director":
                await event.send(T.NOT_FOR_ROLE)
                return
            set_state(user_id, {"action": "wait_school"})
            await event.send(T.DIR_ASK_SCHOOL)
            return
        if payload == "dir_teacher":
            if user["role"] not in ["director", "zavuch"]:
                await event.send(T.NOT_FOR_ROLE)
                return
            set_state(user_id, {"action": "wait_teacher"})
            await event.send(T.DIR_ASK_TEACHER)
            return
        if payload == "dir_fire":
            if user["role"] != "director":
                await event.send(T.NOT_FOR_ROLE)
                return
            set_state(user_id, {"action": "wait_fire"})
            await event.send(T.DIR_ASK_FIRE)
            return
        if payload == "dir_zavuch":
            if user["role"] != "director":
                await event.send(T.NOT_FOR_ROLE)
                return
            set_state(user_id, {"action": "wait_zavuch"})
            await event.send(T.DIR_ASK_ZAVUCH)
            return

        if payload == "zavuch_excel":
            if user["role"] != "zavuch":
                await event.send(T.NOT_FOR_ROLE)
                return
            set_state(user_id, {"action": "wait_excel_file"})
            await event.send(T.ZAVUCH_ASK_EXCEL)
            return

        if payload == "teach_class":
            if user["role"] != "teacher":
                await event.send(T.NOT_FOR_ROLE)
                return
            if user["class_id"]:
                await event.send(T.TEACH_CLASS_EXISTS)
                return
            set_state(user_id, {"action": "wait_new_class"})
            await event.send(T.TEACH_ASK_CLASS)
            return

        if payload == "teach_codes":
            if user["role"] != "teacher":
                await event.send(T.NOT_FOR_ROLE)
                return
            classes = db.get_classes_of_teacher(user_id)
            if not classes:
                await event.send(T.TEACH_CODES_EMPTY)
                return
            for c in classes:
                link = class_link(c["invite_code"])
                await event.send(
                    T.teach_codes_row(c["name"], c["invite_code"], link)
                )
            return

        if payload == "teach_add_sched":
            if not user["class_id"]:
                await event.send("Сначала создайте класс.")
                return
            set_state(user_id, {"action": "wait_sched_day"})
            await event.send(T.TEACH_ASK_DAY)
            return
        if payload == "teach_view_sched":
            await event.send(format_schedule(db.get_schedule(user["class_id"])))
            return
        if payload == "teach_reqs":
            reqs = db.get_pending_requests(user["class_id"])
            if not reqs:
                await event.send(T.TEACH_REQ_EMPTY)
                return
            for r in reqs:
                stud = db.get_user(r["user_id"])
                name = stud["name"] if stud else "Неизвестный"
                b = InlineKeyboardBuilder()
                b.row(CallbackButton(text="✅ Принять", payload=f"yes_{r['id']}"))
                b.row(CallbackButton(text="❌ Отклонить", payload=f"no_{r['id']}"))
                await event.send(
                    T.TEACH_REQ_HEADER.format(name=name, uid=r["user_id"]),
                    attachments=[b.as_markup()],
                )
            return
        if payload == "teach_studs":
            studs = db.get_class_students(user["class_id"])
            if not studs:
                await event.send(T.TEACH_STUDS_EMPTY)
                return
            for s in studs:
                stud = db.get_user(s["user_id"])
                name = stud["name"] if stud else "Неизвестный"
                b = InlineKeyboardBuilder()
                b.row(CallbackButton(text="🚫 Исключить", payload=f"kick_{s['user_id']}"))
                await event.send(
                    T.TEACH_STUD_ROW.format(name=name, uid=s["user_id"]),
                    attachments=[b.as_markup()],
                )
            return
        if payload == "teach_del_sched":
            sched = db.get_schedule(user["class_id"])
            if not sched:
                await event.send(T.TEACH_DELETE_EMPTY)
                return
            for row in sched:
                b = InlineKeyboardBuilder()
                b.row(CallbackButton(text="🗑️ Удалить", payload=f"delsch_{row['id']}"))
                await event.send(
                    f"{DAYS[row['day_of_week']]} | {row['time']} — {row['subject']}",
                    attachments=[b.as_markup()],
                )
            return
            
        if payload == "teach_hw":
            if not user["class_id"]:
                await event.send("Сначала создайте класс.")
                return
            set_state(user_id, {"action": "wait_hw_text"})
            await event.send(T.TEACH_ASK_HW)
            return

        if payload.startswith("delsch_"):
            lesson_id = payload.split("_")[1]
            lesson = db.get_schedule(user["class_id"])
            if any(l["id"] == lesson_id for l in lesson):
                db.delete_lesson(lesson_id)
                await event.send(T.TEACH_DELETE_OK)
            else:
                await event.send("Урок не найден в вашем классе.")
            return

        if payload.startswith("yes_"):
            req_id = payload.split("_")[1]
            req = db.get_request(req_id)
            if not req or req["class_id"] != user["class_id"]:
                await event.send("Эта заявка не из вашего класса.")
                return
            db.approve_request(req_id)
            await event.send(T.TEACH_REQ_OK)
            try:
                await bot.send_message(
                    chat_id=int(req["user_id"]),
                    text="🎉 Учитель принял вашу заявку в класс! "
                         "Теперь вы видите расписание в /menu.",
                )
            except Exception as e:
                log.warning("Не удалось уведомить ученика %s: %s", req["user_id"], e)
            return
        if payload.startswith("no_"):
            req_id = payload.split("_")[1]
            req = db.get_request(req_id)
            if not req or req["class_id"] != user["class_id"]:
                await event.send("Эта заявка не из вашего класса.")
                return
            db.reject_request(req_id)
            await event.send(T.TEACH_REQ_NO)
            return
        if payload.startswith("kick_"):
            uid = payload.split("_")[1]
            students = db.get_class_students(user["class_id"])
            if any(s["user_id"] == uid for s in students):
                db.kick_student(uid, user["class_id"])
                await event.send(T.TEACH_KICK_OK)
                try:
                    await bot.send_message(
                        chat_id=int(uid),
                        text="Учитель исключил вас из класса. "
                             "Если это ошибка — свяжитесь с учителем.",
                    )
                except Exception as e:
                    log.warning("Не удалось уведомить ученика %s: %s", uid, e)
            else:
                await event.send("Ученик не найден в вашем классе.")
            return

        if payload == "stud_add":
            set_state(user_id, {"action": "wait_task"})
            await event.send(T.STUD_ASK_TASK)
            return
        if payload == "stud_ovz":
            new_val = 0 if user["ovz"] else 1
            db.update_user(user_id, "ovz", new_val)
            await event.send(T.STUD_OVZ_ON if new_val else T.STUD_OVZ_OFF)
            return
        if payload == "stud_sched":
            if not user["class_id"]:
                await event.send(
                    "Вы пока не в классе. Получите у учителя ссылку или код "
                    "и напишите: школа КОД"
                )
                return
            await event.send(format_schedule(db.get_schedule(user["class_id"])))
            return
        if payload == "stud_tasks":
            if user["ovz"] == 1:
                task = db.get_first_pending_task(user_id)
                if not task:
                    await event.send("Все задачи выполнены! Молодец! 🌟")
                    return
                
                deadline_info = f"\n⏰ Дедлайн: {task['deadline']}" if task['deadline'] else ""
                b = InlineKeyboardBuilder()
                b.row(CallbackButton(text="✅ Сделано", payload=f"task_{task['id']}"))
                await event.send(
                    T.STUD_OVZ_ROW.format(subject=task["subject"], title=task["title"]) + deadline_info,
                    attachments=[b.as_markup()],
                )
                return
            tasks = db.get_tasks(user_id)
            pending = [t for t in tasks if not t["is_done"]]
            if not pending:
                await event.send(T.STUD_TASKS_EMPTY)
                return
            for t in pending:
                deadline_info = f"\n⏰ Дедлайн: {t['deadline']}" if t['deadline'] else ""
                b = InlineKeyboardBuilder()
                b.row(CallbackButton(text="✅ Выполнено", payload=f"task_{t['id']}"))
                await event.send(
                    T.STUD_TASK_ROW.format(subject=t["subject"], title=t["title"]) + deadline_info,
                    attachments=[b.as_markup()],
                )
            return
        if payload.startswith("task_"):
            task_id = payload.split("_")[1]
            owner = db.complete_task(task_id)
            if owner:
                await event.send(T.STUD_TASK_DONE)
                task = db.get_task(task_id)
                title = task["title"] if task else "задачу"
                for parent_row in db.get_parents_of(owner):
                    try:
                        await bot.send_message(
                            chat_id=int(parent_row["id"]),
                            text=f"✅ Ваш ребёнок выполнил задачу: {title}",
                        )
                    except Exception as e:
                        log.warning(
                            "Не удалось уведомить родителя %s: %s",
                            parent_row["id"], e,
                        )
            else:
                await event.send(T.STUD_TASK_ALREADY)
            return

        if payload == "parent_link":
            set_state(user_id, {"action": "wait_child_link"})
            await event.send(T.PARENT_ASK_CHILD)
            return
        if payload == "parent_progress":
            if not user["child_id"]:
                await event.send(T.PARENT_NEED_CHILD)
                return
            child = db.get_user(user["child_id"])
            if not child or child["role"] != "student":
                await event.send("Ребёнок не найден или не является учеником. Привяжите заново.")
                return
            stats = db.get_progress(child["id"])
            await event.send(T.PARENT_PROGRESS.format(
                name=child["name"], done=stats["done"],
                total=stats["total"], points=child["points"],
            ))
            return
        if payload == "parent_add_task":
            if not user["child_id"]:
                await event.send(T.PARENT_NEED_CHILD)
                return
            set_state(user_id, {"action": "wait_parent_task"})
            await event.send(T.PARENT_ASK_TASK)
            return

        await event.send(T.UNKNOWN)