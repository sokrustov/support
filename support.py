import logging
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ChatType

# Загрузка конфигурации
load_dotenv()
TOKEN = os.getenv("SUPPORT_BOT_TOKEN")
SUPPORT_CHAT_ID = int(os.getenv("SUPPORT_CHAT_ID"))
OWNER_ID = int(os.getenv("OWNER_ID"))
DB_FILE = "support_db.json"
LOGS_THREAD_ID = 743  # ID канала логов в группе

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


class SupportDB:
    def __init__(self, filename):
        self.filename = filename
        self.data = self.load()

    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Инициализация ключей
                    for key in ["tickets", "active_chats", "banned", "agents", "ban_reasons", "user_metadata",
                                "complaints"]:
                        if key not in data:
                            data[key] = {} if key != "banned" else []
                    return data
            except:
                pass
        return {"tickets": {}, "active_chats": {}, "banned": [], "agents": {}, "ban_reasons": {}, "user_metadata": {},
                "complaints": {}}

    def save(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def register_user(self, user):
        uid = str(user.id)
        if uid not in self.data["user_metadata"]:
            self.data["user_metadata"][uid] = {
                "username": user.username,
                "ticket_count": 0
            }
        else:
            self.data["user_metadata"][uid]["username"] = user.username
        self.save()

    def increment_ticket(self, user_id):
        uid = str(user_id)
        if uid in self.data["user_metadata"]:
            self.data["user_metadata"][uid]["ticket_count"] += 1
            self.save()

    def get_all_user_ids(self):
        """Возвращает список всех user_id из базы"""
        return list(self.data["user_metadata"].keys())

    def add_broadcast_log(self, log_data):
        """Добавляет лог рассылки"""
        if "broadcast_logs" not in self.data:
            self.data["broadcast_logs"] = []
        self.data["broadcast_logs"].append(log_data)
        # Храним только последние 50 логов
        if len(self.data["broadcast_logs"]) > 50:
            self.data["broadcast_logs"] = self.data["broadcast_logs"][-50:]
        self.save()

    def get_broadcast_logs(self, limit=10):
        """Возвращает последние логи рассылок"""
        if "broadcast_logs" not in self.data:
            return []
        return list(reversed(self.data["broadcast_logs"][-limit:]))


db = SupportDB(DB_FILE)


# --- ФУНКЦИЯ ЛОГИРОВАНИЯ ---
async def send_log(context: ContextTypes.DEFAULT_TYPE, log_type: str, data: dict):
    """
    Отправка логов в канал логов

    log_type: ticket_created, ticket_taken, ticket_closed, ticket_closed_by_user, user_banned, user_unbanned,
              agent_assigned, agent_removed, complaint_created, complaint_taken, complaint_closed,
              complaint_closed_by_user, agent_message_sent, broadcast_sent
    """
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    if log_type == "ticket_created":
        text = (
            f"📩 <b>СОЗДАНО ОБРАЩЕНИЕ</b>\n\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code> | @{data['username']}\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "ticket_taken":
        # Формируем ссылку на тему
        thread_link = f"https://t.me/c/{str(SUPPORT_CHAT_ID)[4:]}/{data['thread_id']}"

        text = (
            f"👁 <b>НА РАССМОТРЕНИИ</b>\n\n"
            f"👨‍💻 <b>Агент:</b> #{data['agent_num']} | @{data['agent_username']} | <code>{data['agent_id']}</code>\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code>\n"
            f"🔗 <b>Обращение:</b> <a href='{thread_link}'>Перейти</a>\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "ticket_closed":
        text = (
            f"🔴 <b>ОБРАЩЕНИЕ ЗАКРЫТО</b>\n\n"
            f"👨‍💻 <b>Закрыл:</b> #{data['agent_num']} | @{data['agent_username']} | <code>{data['agent_id']}</code>\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code>\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "ticket_closed_by_user":
        text = (
            f"⚪️ <b>ОБРАЩЕНИЕ ЗАКРЫТО ПОЛЬЗОВАТЕЛЕМ</b>\n\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code> | @{data['username']}\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "user_banned":
        text = (
            f"🚫 <b>ПОЛЬЗОВАТЕЛЬ ЗАБЛОКИРОВАН</b>\n\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code> | @{data['username']}\n"
            f"👨‍💻 <b>Агент:</b> #{data['agent_num']} | @{data['agent_username']} | <code>{data['agent_id']}</code>\n"
            f"📝 <b>Причина:</b> {data['reason']}\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "user_unbanned":
        text = (
            f"✅ <b>ПОЛЬЗОВАТЕЛЬ РАЗБЛОКИРОВАН</b>\n\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code> | @{data['username']}\n"
            f"👨‍💻 <b>Агент:</b> #{data['agent_num']} | @{data['agent_username']} | <code>{data['agent_id']}</code>\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "agent_assigned":
        text = (
            f"🎯 <b>АГЕНТ НАЗНАЧЕН</b>\n\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code> | @{data['username']}\n"
            f"👨‍💻 <b>Присвоен номер:</b> #{data['agent_num']}\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "agent_removed":
        text = (
            f"❌ <b>АГЕНТ СНЯТ</b>\n\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code> | @{data['username']}\n"
            f"👨‍💻 <b>Снят номер:</b> #{data['agent_num']}\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "complaint_created":
        text = (
            f"⚠️ <b>СОЗДАНА ЖАЛОБА НА АГЕНТА</b>\n\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code> | @{data['username']}\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "complaint_taken":
        # Формируем ссылку на тему
        thread_link = f"https://t.me/c/{str(SUPPORT_CHAT_ID)[4:]}/{data['thread_id']}"

        text = (
            f"👁 <b>ЖАЛОБА НА РАССМОТРЕНИИ</b>\n\n"
            f"👨‍💻 <b>Принял:</b> Owner | @{data['agent_username']} | <code>{data['agent_id']}</code>\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code>\n"
            f"🔗 <b>Жалоба:</b> <a href='{thread_link}'>Перейти</a>\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "complaint_closed":
        text = (
            f"🔴 <b>ЖАЛОБА ЗАКРЫТА</b>\n\n"
            f"👨‍💻 <b>Закрыл:</b> Owner | @{data['agent_username']} | <code>{data['agent_id']}</code>\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code>\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "complaint_closed_by_user":
        text = (
            f"⚪️ <b>ЖАЛОБА ЗАКРЫТА ПОЛЬЗОВАТЕЛЕМ</b>\n\n"
            f"👤 <b>Пользователь:</b> <code>{data['user_id']}</code> | @{data['username']}\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "agent_message_sent":
        text = (
            f"📤 <b>СООБЩЕНИЕ ОТ АГЕНТА</b>\n\n"
            f"👨‍💻 <b>Агент:</b> #{data['agent_num']} | @{data['agent_username']} | <code>{data['agent_id']}</code>\n"
            f"👤 <b>Получатель:</b> <code>{data['user_id']}</code> | @{data['username']}\n"
            f"💬 <b>Сообщение:</b> {data['message'][:100]}{'...' if len(data['message']) > 100 else ''}\n"
            f"🕐 <b>Время:</b> {now}"
        )

    elif log_type == "broadcast_sent":
        text = (
            f"📣 <b>МАССОВАЯ РАССЫЛКА</b>\n\n"
            f"👨‍💻 <b>Отправитель:</b> Owner | @{data['sender_username']} | <code>{data['sender_id']}</code>\n"
            f"👥 <b>Получателей:</b> {data['total_users']}\n"
            f"✅ <b>Доставлено:</b> {data['success_count']}\n"
            f"❌ <b>Ошибок:</b> {data['fail_count']}\n"
            f"💬 <b>Сообщение:</b> {data['message'][:100]}{'...' if len(data['message']) > 100 else ''}\n"
            f"🕐 <b>Время:</b> {now}"
        )

    else:
        return

    try:
        await context.bot.send_message(
            chat_id=SUPPORT_CHAT_ID,
            message_thread_id=LOGS_THREAD_ID,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Failed to send log: {e}")


# --- КЛАВИАТУРЫ ---
def get_admin_kb(uid, is_closed=False, is_complaint=False):
    uid_str = str(uid)
    buttons = []
    if not is_closed:
        is_active = uid_str in db.data.get("active_chats", {})
        # Для жалоб только owner может взять
        if not is_active and not is_complaint:
            buttons.append([InlineKeyboardButton("👨‍💻 Рассмотреть", callback_data=f"take_{uid}")])
        elif not is_active and is_complaint:
            buttons.append([InlineKeyboardButton("👨‍💻 Рассмотреть (Owner)", callback_data=f"take_complaint_{uid}")])
        buttons.append([InlineKeyboardButton("✅ Закрыть", callback_data=f"close_{uid}_{1 if is_complaint else 0}")])

    is_banned = int(uid) in db.data.get("banned", [])
    ban_btn_text = "🔑 Разблокировать" if is_banned else "🔑 Заблокировать"
    ban_callback = f"unban_{uid}" if is_banned else f"ban_{uid}"
    buttons.append([InlineKeyboardButton(ban_btn_text, callback_data=ban_callback)])
    return InlineKeyboardMarkup(buttons)


def get_owner_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Все пользователи", callback_data="adm_users_list")],
        [InlineKeyboardButton("🛠 Добавить агента", callback_data="adm_request")],
        [InlineKeyboardButton("🗑 Удалить агента", callback_data="adm_remove")],
        [InlineKeyboardButton("🎧 Список агентов", callback_data="adm_list")],
        [InlineKeyboardButton("📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton("📣 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton("📜 Логи рассылок", callback_data="adm_broadcast_logs")],
        [InlineKeyboardButton("✉️ Написать пользователю", callback_data="adm_send_msg")]
    ])


def get_user_close_kb(is_complaint=False):
    text = "✅ Закрыть жалобу" if is_complaint else "✅ Закрыть обращение"
    callback = "user_close_complaint" if is_complaint else "user_close_self"
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=callback)]])


def get_agent_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Заблокировать по ID", callback_data="agent_ban_by_id")],
        [InlineKeyboardButton("✅ Разблокировать по ID", callback_data="agent_unban_by_id")],
        [InlineKeyboardButton("📋 Обращения пользователя", callback_data="agent_view_tickets")],
        [InlineKeyboardButton("✉️ Написать пользователю", callback_data="agent_send_msg")]
    ])


def get_start_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ Жалоба на агента", callback_data="create_complaint")]
    ])


# --- ХЕНДЛЕРЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE: return
    user = update.effective_user
    db.register_user(user)
    await update.message.reply_text(
        "👋 Здравствуйте! Опишите вашу проблему или подайте жалобу на агента.",
        reply_markup=get_start_kb()
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin с кнопками управления"""
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text("🛠 <b>Панель управления</b>", parse_mode="HTML", reply_markup=get_owner_kb())


async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Панель агента"""
    if update.effective_chat.id != SUPPORT_CHAT_ID: return
    user_id = str(update.effective_user.id)
    if user_id in db.data.get("agents", {}) or update.effective_user.id == OWNER_ID:
        await update.message.reply_text("<b>Панель агента</b>", parse_mode="HTML", reply_markup=get_agent_panel_kb())


async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    uid_str = str(user.id)

    # Проверка бана
    if chat.type == ChatType.PRIVATE and user.id in db.data.get("banned", []):
        await update.message.reply_text("🔑 Вы заблокированы в поддержке.")
        return

    # --- Обработка сообщений в чате поддержки ---
    if chat.id == SUPPORT_CHAT_ID:
        agent_id = str(update.effective_user.id)
        is_agent = agent_id in db.data.get("agents", {})
        is_owner = update.effective_user.id == OWNER_ID

        # Обработка рассылки
        if is_owner and context.user_data.get('waiting_broadcast'):
            broadcast_text = update.message.text
            all_users = db.get_all_user_ids()
            total_users = len(all_users)

            if total_users == 0:
                await update.message.reply_text("❌ В базе нет пользователей для рассылки.")
                context.user_data.pop('waiting_broadcast', None)
                return

            status_msg = await update.message.reply_text(
                f"📣 Начинаю массовую рассылку...\n"
                f"👥 Всего пользователей: {total_users}\n\n"
                f"Пожалуйста, подождите..."
            )

            success_count = 0
            fail_count = 0
            message_to_send = f"📣 <b>Сообщение от администрации:</b>\n\n{broadcast_text}"

            for user_id in all_users:
                try:
                    await context.bot.send_message(
                        chat_id=int(user_id),
                        text=message_to_send,
                        parse_mode="HTML"
                    )
                    success_count += 1
                except Exception as e:
                    fail_count += 1
                    logger.warning(f"Failed to send broadcast to {user_id}: {e}")

            await status_msg.edit_text(
                f"✅ <b>Рассылка завершена!</b>\n\n"
                f"👥 Всего пользователей: {total_users}\n"
                f"✅ Доставлено: {success_count}\n"
                f"❌ Ошибок: {fail_count}",
                parse_mode="HTML"
            )

            sender_username = db.data.get("user_metadata", {}).get(str(OWNER_ID), {}).get("username", "Неизвестно")
            await send_log(context, "broadcast_sent", {
                "sender_id": str(OWNER_ID),
                "sender_username": sender_username,
                "total_users": total_users,
                "success_count": success_count,
                "fail_count": fail_count,
                "message": broadcast_text
            })

            # Сохраняем лог рассылки в БД
            db.add_broadcast_log({
                "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                "sender_id": str(OWNER_ID),
                "sender_username": sender_username,
                "total_users": total_users,
                "success": success_count,
                "failed": fail_count,
                "message": broadcast_text[:100] + "..." if len(broadcast_text) > 100 else broadcast_text
            })

            context.user_data.pop('waiting_broadcast', None)
            return

        # Обработка ввода ID для отправки сообщения (Owner)
        if is_owner and context.user_data.get('waiting_msg_id'):
            target_user_id = update.message.text.strip()
            if target_user_id.isdigit():
                context.user_data['msg_target_user'] = target_user_id
                context.user_data['waiting_msg_text'] = True
                context.user_data.pop('waiting_msg_id', None)
                await update.message.reply_text("✉️ Теперь введите текст сообщения:")
            else:
                await update.message.reply_text("❌ ID должен быть числом. Попробуйте снова:")
            return

        # Обработка отправки сообщения пользователю (Owner)
        if is_owner and context.user_data.get('waiting_msg_text'):
            target_user_id = context.user_data.get('msg_target_user')
            message_text = update.message.text

            full_message = f"💬 <b>Сообщение от Owner:</b>\n\n{message_text}"

            try:
                await context.bot.send_message(
                    chat_id=int(target_user_id),
                    text=full_message,
                    parse_mode="HTML"
                )

                await update.message.reply_text(
                    f"✅ Сообщение успешно отправлено пользователю {target_user_id}"
                )

                sender_username = db.data.get("user_metadata", {}).get(str(OWNER_ID), {}).get("username", "Неизвестно")
                target_username = db.data.get("user_metadata", {}).get(target_user_id, {}).get("username", "Неизвестно")

                await send_log(context, "agent_message_sent", {
                    "agent_id": str(OWNER_ID),
                    "agent_num": "Owner",
                    "agent_username": sender_username,
                    "user_id": target_user_id,
                    "username": target_username,
                    "message": message_text
                })

            except Exception as e:
                logger.error(f"Failed to send message to user {target_user_id}: {e}")
                await update.message.reply_text(
                    f"❌ Не удалось отправить сообщение пользователю {target_user_id}"
                )

            context.user_data.pop('waiting_msg_text', None)
            context.user_data.pop('msg_target_user', None)
            return

        # Обработка ввода ID для отправки сообщения (Agent)
        if is_agent and context.user_data.get('waiting_agent_msg_id'):
            target_user_id = update.message.text.strip()
            if target_user_id.isdigit():
                context.user_data['agent_msg_target_user'] = target_user_id
                context.user_data['waiting_agent_msg_text'] = True
                context.user_data.pop('waiting_agent_msg_id', None)
                await update.message.reply_text("✉️ Теперь введите текст сообщения:")
            else:
                await update.message.reply_text("❌ ID должен быть числом. Попробуйте снова:")
            return

        # Обработка отправки сообщения пользователю (Agent)
        if is_agent and context.user_data.get('waiting_agent_msg_text'):
            target_user_id = context.user_data.get('agent_msg_target_user')
            message_text = update.message.text
            agent_num = db.data["agents"][agent_id]["num"]

            full_message = f"💬 <b>Сообщение от агента #{agent_num}:</b>\n\n{message_text}"

            try:
                await context.bot.send_message(
                    chat_id=int(target_user_id),
                    text=full_message,
                    parse_mode="HTML"
                )

                await update.message.reply_text(
                    f"✅ Сообщение успешно отправлено пользователю {target_user_id}\n"
                    f"От: Агент #{agent_num}"
                )

                agent_username = db.data.get("user_metadata", {}).get(agent_id, {}).get("username", "Неизвестно")
                target_username = db.data.get("user_metadata", {}).get(target_user_id, {}).get("username", "Неизвестно")

                await send_log(context, "agent_message_sent", {
                    "agent_id": agent_id,
                    "agent_num": agent_num,
                    "agent_username": agent_username,
                    "user_id": target_user_id,
                    "username": target_username,
                    "message": message_text
                })

            except Exception as e:
                logger.error(f"Failed to send message to user {target_user_id}: {e}")
                await update.message.reply_text(
                    f"❌ Не удалось отправить сообщение пользователю {target_user_id}"
                )

            context.user_data.pop('waiting_agent_msg_text', None)
            context.user_data.pop('agent_msg_target_user', None)
            return

        # Добавление агента владельцем
        if is_owner and context.user_data.get('waiting_agent'):
            agent_id_to_add = update.message.text.strip()
            if agent_id_to_add.isdigit():
                num = len(db.data["agents"]) + 1
                db.data["agents"][agent_id_to_add] = {"num": num, "replies": 0, "bans": 0}
                db.save()

                # Регистрируем пользователя, чтобы получить его username
                try:
                    target_user = await context.bot.get_chat(int(agent_id_to_add))
                    db.register_user(target_user)
                    username = target_user.username or "Неизвестно"
                except Exception as e:
                    username = "Неизвестно"
                    logger.warning(f"Could not fetch user {agent_id_to_add}: {e}")

                await update.message.reply_text(f"✅ Агент #{num} добавлен.")

                # Лог добавления агента
                await send_log(context, "agent_assigned", {
                    "user_id": agent_id_to_add,
                    "username": username,
                    "agent_num": num
                })

                context.user_data.pop('waiting_agent', None)
            else:
                await update.message.reply_text("❌ ID должен быть числом.")
            return

        # Удаление агента
        if is_owner and context.user_data.get('waiting_remove_agent'):
            agent_id_to_remove = update.message.text.strip()
            if agent_id_to_remove in db.data["agents"]:
                agent_num = db.data["agents"][agent_id_to_remove]["num"]
                username = db.data.get("user_metadata", {}).get(agent_id_to_remove, {}).get("username", "Неизвестно")

                db.data["agents"].pop(agent_id_to_remove)
                db.save()
                await update.message.reply_text(f"✅ Агент #{agent_num} удалён.")

                # Лог удаления агента
                await send_log(context, "agent_removed", {
                    "user_id": agent_id_to_remove,
                    "username": username,
                    "agent_num": agent_num
                })

                context.user_data.pop('waiting_remove_agent', None)
            else:
                await update.message.reply_text("❌ Пользователь не является агентом.")
            return

        # Разбан по ID
        if context.user_data.get('waiting_unban_id'):
            target_uid = update.message.text.strip()
            if not target_uid.isdigit():
                await update.message.reply_text("❌ ID должен быть числом.")
                return

            if int(target_uid) not in db.data["banned"]:
                await update.message.reply_text("⚠️ Пользователь не заблокирован.")
                return

            # Разбан пользователя
            db.data["banned"].remove(int(target_uid))
            db.data["ban_reasons"].pop(target_uid, None)
            db.save()

            # Определяем агента
            agent_db_id = agent_id if is_agent else str(OWNER_ID)
            agent_num = db.data["agents"][agent_id]["num"] if is_agent else "Owner"
            agent_display_name = f"Агент #{agent_num}" if is_agent else "Owner"
            agent_username = db.data.get("user_metadata", {}).get(agent_db_id, {}).get("username", "Неизвестно")

            # Получаем username разблокированного пользователя
            username = db.data.get("user_metadata", {}).get(target_uid, {}).get("username", "Неизвестно")

            # Уведомление пользователя о разбане
            try:
                await context.bot.send_message(
                    int(target_uid),
                    f"✅ Вы были разблокированы агентом #{agent_num}.\nТеперь вы можете снова обращаться в поддержку."
                )
            except Exception as e:
                logger.info(f"Could not notify user {target_uid} of unban: {e}")

            await update.message.reply_text(f"✅ Пользователь {target_uid} разблокирован {agent_display_name}.")

            # Лог разбана
            await send_log(context, "user_unbanned", {
                "user_id": target_uid,
                "username": username,
                "agent_num": agent_num,
                "agent_username": agent_username,
                "agent_id": agent_db_id
            })

            context.user_data.pop('waiting_unban_id', None)

            # Обновить клавиатуру в тикете
            ticket = db.data.get("tickets", {}).get(target_uid)
            if ticket and ticket.get("admin_msg_id"):
                try:
                    await context.bot.edit_message_reply_markup(
                        SUPPORT_CHAT_ID, ticket["admin_msg_id"], reply_markup=get_admin_kb(target_uid)
                    )
                except Exception as e:
                    logger.error(f"Failed to update unban button for {target_uid}: {e}")
            return

        # Ввод причины бана
        if context.user_data.get('waiting_ban_reason'):
            reason = update.message.text.strip()
            target_uid = context.user_data.get('ban_target')

            # Определяем агента
            agent_db_id = agent_id if is_agent else str(OWNER_ID)
            agent_num = db.data["agents"][agent_id]["num"] if is_agent else "Owner"
            agent_display_name = f"Агент #{agent_num}" if is_agent else "Owner"
            agent_username = db.data.get("user_metadata", {}).get(agent_db_id, {}).get("username", "Неизвестно")

            # Получаем username забаненного пользователя
            username = db.data.get("user_metadata", {}).get(target_uid, {}).get("username", "Неизвестно")

            # Бан пользователя
            db.data["banned"].append(int(target_uid))
            db.data["ban_reasons"][str(target_uid)] = {"reason": reason, "agent_num": agent_num}

            # Увеличиваем счетчик банов агента
            if is_agent:
                db.data["agents"][agent_id]["bans"] += 1

            db.save()

            # Уведомление пользователя
            try:
                await context.bot.send_message(
                    int(target_uid),
                    f"🔑 Вы заблокированы агентом #{agent_num}.\n📝 Причина: {reason}"
                )
            except Exception as e:
                logger.info(f"Could not notify user {target_uid} of ban: {e}")

            await update.message.reply_text(f"🔑 Пользователь {target_uid} заблокирован {agent_display_name}.")

            # Лог бана
            await send_log(context, "user_banned", {
                "user_id": target_uid,
                "username": username,
                "agent_num": agent_num,
                "agent_username": agent_username,
                "agent_id": agent_db_id,
                "reason": reason
            })

            context.user_data.pop('waiting_ban_reason', None)
            context.user_data.pop('ban_target', None)

            # Обновить клавиатуру в тикете, если бан был через кнопку
            if context.user_data.pop('ban_msg_id', None):
                ticket = db.data.get("tickets", {}).get(target_uid)
                if ticket and ticket.get("admin_msg_id"):
                    try:
                        await context.bot.edit_message_reply_markup(
                            SUPPORT_CHAT_ID, ticket["admin_msg_id"], reply_markup=get_admin_kb(target_uid)
                        )
                    except Exception as e:
                        logger.error(f"Failed to update ban button for {target_uid}: {e}")
            return

        # Просмотр тикетов пользователя
        if context.user_data.get('waiting_view_tickets_id'):
            target_uid = update.message.text.strip()
            if not target_uid.isdigit():
                await update.message.reply_text("❌ ID должен быть числом.")
                return

            user_data = db.data.get("user_metadata", {}).get(target_uid)
            if not user_data:
                await update.message.reply_text("⚠️ Пользователь не найден.")
                return

            ticket_count = user_data.get('ticket_count', 0)
            username = user_data.get('username', 'Неизвестно')
            is_banned = int(target_uid) in db.data["banned"]
            status = "🔴 BANNED" if is_banned else "✅ Active"

            result = (
                f"📋 <b>Информация о пользователе</b>\n\n"
                f"ID: <code>{target_uid}</code>\n"
                f"Username: @{username}\n"
                f"Статус: {status}\n"
                f"Всего обращений: {ticket_count}"
            )
            await update.message.reply_text(result, parse_mode="HTML")
            context.user_data.pop('waiting_view_tickets_id', None)
            return

        # Если сообщение в теме обращения - пересылаем пользователю
        thread_id = update.message.message_thread_id
        if thread_id:
            target_uid = None
            for uid, ticket in db.data.get("tickets", {}).items():
                if ticket.get("thread_id") == thread_id and ticket.get("status") == "open":
                    target_uid = uid
                    break

            if not target_uid:
                for uid, complaint in db.data.get("complaints", {}).items():
                    if complaint.get("thread_id") == thread_id and complaint.get("status") == "open":
                        target_uid = uid
                        break

            if target_uid:
                try:
                    await context.bot.copy_message(chat_id=int(target_uid), from_chat_id=SUPPORT_CHAT_ID,
                                                   message_id=update.message.id)
                    if is_agent:
                        db.data["agents"][agent_id]["replies"] += 1
                        db.save()
                except Exception as e:
                    logger.error(f"Failed to forward message to {target_uid}: {e}")

    # Создание обращения или пересылка сообщения
    elif chat.type == ChatType.PRIVATE:
        # Если пользователь в режиме жалобы
        if context.user_data.get('complaint_mode'):
            if uid_str not in db.data["complaints"] or db.data["complaints"][uid_str].get("status") == "closed":
                topic_name = f"[Agent] {user.id} | @{user.username}" if user.username else f"[Agent] {user.id} | {user.first_name}"
                topic = await context.bot.create_forum_topic(chat_id=SUPPORT_CHAT_ID, name=topic_name)

                sent_msg = await context.bot.send_message(
                    SUPPORT_CHAT_ID,
                    message_thread_id=topic.message_thread_id,
                    text=f"⚠️ <b>Новая жалоба на агента</b>\nID: <code>{user.id}</code>\nЮзер: @{user.username}",
                    parse_mode="HTML",
                    reply_markup=get_admin_kb(uid_str, is_complaint=True)
                )

                db.data["complaints"][uid_str] = {
                    "thread_id": topic.message_thread_id,
                    "status": "open",
                    "admin_msg_id": sent_msg.message_id
                }
                db.save()
                await update.message.reply_text("✅ Ваша жалоба создана.",
                                                reply_markup=get_user_close_kb(is_complaint=True))

                # Лог создания жалобы
                await send_log(context, "complaint_created", {
                    "user_id": user.id,
                    "username": user.username or "Неизвестно"
                })

                context.user_data['complaint_mode'] = False

            await context.bot.copy_message(
                chat_id=SUPPORT_CHAT_ID,
                message_thread_id=db.data["complaints"][uid_str]["thread_id"],
                from_chat_id=user.id,
                message_id=update.message.id
            )
        else:
            # Обычное обращение
            if uid_str not in db.data["tickets"] or db.data["tickets"][uid_str].get("status") == "closed":
                db.increment_ticket(user.id)
                topic_name = f"{user.id} | @{user.username}" if user.username else f"{user.id} | {user.first_name}"
                topic = await context.bot.create_forum_topic(chat_id=SUPPORT_CHAT_ID, name=topic_name)

                sent_msg = await context.bot.send_message(
                    SUPPORT_CHAT_ID,
                    message_thread_id=topic.message_thread_id,
                    text=f"🆕 <b>Новое обращение</b>\nID: <code>{user.id}</code>\nЮзер: @{user.username}",
                    parse_mode="HTML",
                    reply_markup=get_admin_kb(uid_str)
                )

                db.data["tickets"][uid_str] = {
                    "thread_id": topic.message_thread_id,
                    "status": "open",
                    "admin_msg_id": sent_msg.message_id
                }
                db.save()
                await update.message.reply_text("✅ Ваше обращение создано.", reply_markup=get_user_close_kb())

                # Лог создания тикета
                await send_log(context, "ticket_created", {
                    "user_id": user.id,
                    "username": user.username or "Неизвестно"
                })

            await context.bot.copy_message(
                chat_id=SUPPORT_CHAT_ID,
                message_thread_id=db.data["tickets"][uid_str]["thread_id"],
                from_chat_id=user.id,
                message_id=update.message.id
            )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    uid_str = str(user_id)
    data = query.data
    await query.answer()

    # Создание жалобы
    if data == "create_complaint":
        context.user_data['complaint_mode'] = True
        await query.edit_message_text("⚠️ Опишите вашу жалобу на агента.")
        return

    # Закрытие пользователем обращения
    if data == "user_close_self":
        ticket = db.data["tickets"].get(uid_str)
        if ticket and ticket["status"] == "open":
            db.data["tickets"][uid_str]["status"] = "closed"
            db.data["active_chats"].pop(uid_str, None)
            db.save()

            username = db.data.get("user_metadata", {}).get(uid_str, {}).get("username", "Неизвестно")

            await query.edit_message_text("🔴 Вы закрыли обращение.")
            await context.bot.send_message(SUPPORT_CHAT_ID, message_thread_id=ticket["thread_id"],
                                           text="⚪️ Пользователь закрыл обращение.")
            await context.bot.close_forum_topic(SUPPORT_CHAT_ID, ticket["thread_id"])

            # Лог закрытия обращения пользователем
            await send_log(context, "ticket_closed_by_user", {
                "user_id": uid_str,
                "username": username
            })

            if ticket.get("admin_msg_id"):
                try:
                    await context.bot.edit_message_reply_markup(SUPPORT_CHAT_ID, ticket["admin_msg_id"],
                                                                reply_markup=get_admin_kb(uid_str, True))
                except:
                    pass
        return

    # Закрытие пользователем жалобы
    if data == "user_close_complaint":
        complaint = db.data["complaints"].get(uid_str)
        if complaint and complaint["status"] == "open":
            db.data["complaints"][uid_str]["status"] = "closed"
            db.data["active_chats"].pop(uid_str, None)
            db.save()

            username = db.data.get("user_metadata", {}).get(uid_str, {}).get("username", "Неизвестно")

            await query.edit_message_text("🔴 Вы закрыли жалобу.")
            await context.bot.send_message(SUPPORT_CHAT_ID, message_thread_id=complaint["thread_id"],
                                           text="⚪️ Пользователь закрыл жалобу.")
            await context.bot.close_forum_topic(SUPPORT_CHAT_ID, complaint["thread_id"])

            # Лог закрытия жалобы пользователем
            await send_log(context, "complaint_closed_by_user", {
                "user_id": uid_str,
                "username": username
            })

            if complaint.get("admin_msg_id"):
                try:
                    await context.bot.edit_message_reply_markup(SUPPORT_CHAT_ID, complaint["admin_msg_id"],
                                                                reply_markup=get_admin_kb(uid_str, True,
                                                                                          is_complaint=True))
                except:
                    pass
        return

    # Функции панели агента
    if data.startswith("agent_"):
        if uid_str not in db.data.get("agents", {}) and user_id != OWNER_ID:
            await query.answer("Доступ запрещен.", show_alert=True)
            return

        if data == "agent_ban_by_id":
            context.user_data['waiting_ban_id'] = True
            await query.edit_message_text("Введите ID пользователя для блокировки:")
        elif data == "agent_unban_by_id":
            context.user_data['waiting_unban_id'] = True
            await query.edit_message_text("Введите ID пользователя для разблокировки:")
        elif data == "agent_view_tickets":
            context.user_data['waiting_view_tickets_id'] = True
            await query.edit_message_text("Введите ID пользователя для просмотра его обращений:")
        elif data == "agent_send_msg":
            context.user_data['waiting_agent_msg_id'] = True
            await query.edit_message_text("✉️ Введите ID пользователя для отправки сообщения:")
        return

    # Админские функции
    if data.startswith("adm_"):
        if user_id != OWNER_ID: return

        if data == "adm_broadcast":
            context.user_data['waiting_broadcast'] = True
            await query.message.reply_text("📣 Введите текст для массовой рассылки всем пользователям:")
            return

        if data == "adm_send_msg":
            context.user_data['waiting_msg_id'] = True
            await query.message.reply_text("✉️ Введите ID пользователя для отправки сообщения:")
            return

        if data == "adm_users_list":
            users = db.data.get("user_metadata", {})
            res = "👥 <b>Список пользователей:</b>\n\n"
            for uid, info in list(users.items())[:50]:  # Ограничение 50 для читаемости
                status = "🔴 (BANNED)" if int(uid) in db.data["banned"] else ""
                res += f"• <code>{uid}</code> | @{info.get('username')} | Обращений: {info.get('ticket_count')} {status}\n"
            if len(users) > 50:
                res += f"\n... и ещё {len(users) - 50} пользователей"
            await query.message.reply_text(res, parse_mode="HTML")
        elif data == "adm_request":
            context.user_data['waiting_agent'] = True
            await query.message.reply_text("Введите ID агента:")
        elif data == "adm_remove":
            context.user_data['waiting_remove_agent'] = True
            await query.message.reply_text("Введите ID агента для удаления:")
        elif data == "adm_list":
            agents = db.data.get("agents", {})
            if not agents:
                await query.message.reply_text("📋 Список агентов пуст.")
            else:
                res = "🎧 <b>Список агентов:</b>\n\n"
                for aid, info in agents.items():
                    username = db.data.get("user_metadata", {}).get(aid, {}).get("username", "Неизвестно")
                    res += f"• Агент #{info['num']} | <code>{aid}</code> | @{username}\n"
                    res += f"  └ Ответов: {info.get('replies', 0)} | Банов: {info.get('bans', 0)}\n\n"
                await query.message.reply_text(res, parse_mode="HTML")
        elif data == "adm_stats":
            total_tickets = sum(info.get('ticket_count', 0) for info in db.data.get("user_metadata", {}).values())
            total_users = len(db.data.get("user_metadata", {}))
            total_banned = len(db.data.get("banned", []))
            total_agents = len(db.data.get("agents", {}))
            total_complaints = len([c for c in db.data.get("complaints", {}).values()])

            res = (
                f"📊 <b>Статистика системы:</b>\n\n"
                f"👥 Пользователей: {total_users}\n"
                f"📩 Обращений создано: {total_tickets}\n"
                f"⚠️ Жалоб создано: {total_complaints}\n"
                f"👨‍💻 Агентов: {total_agents}\n"
                f"🚫 Заблокировано: {total_banned}"
            )
            await query.message.reply_text(res, parse_mode="HTML")
        elif data == "adm_broadcast_logs":
            logs = db.get_broadcast_logs(10)
            if not logs:
                await query.message.reply_text("📜 Логов рассылок пока нет.")
            else:
                res = "📜 <b>Последние 10 рассылок:</b>\n\n"
                for i, log in enumerate(logs, 1):
                    res += (
                        f"{i}. <b>{log['timestamp']}</b>\n"
                        f"   От: @{log['sender_username']} (<code>{log['sender_id']}</code>)\n"
                        f"   👥 Всего: {log['total_users']} | ✅ {log['success']} | ❌ {log['failed']}\n"
                        f"   💬 {log['message']}\n\n"
                    )
                await query.message.reply_text(res, parse_mode="HTML")
        return

    # Проверка, что пользователь - агент или владелец
    if uid_str not in db.data.get("agents", {}) and user_id != OWNER_ID:
        await query.answer("Доступ запрещен.", show_alert=True)
        return

    # Действия агентов
    if data.startswith("take_complaint_"):
        # Только owner может взять жалобу
        if user_id != OWNER_ID:
            await query.answer("Только Owner может взять жалобу!", show_alert=True)
            return

        target_uid = data.split("_")[2]
        db.data["active_chats"][target_uid] = {"agent_num": "Owner"}
        db.save()

        complaint = db.data["complaints"].get(target_uid)
        thread_id = complaint.get("thread_id") if complaint else None

        await query.message.edit_reply_markup(reply_markup=get_admin_kb(target_uid, is_complaint=True))
        await context.bot.send_message(SUPPORT_CHAT_ID, message_thread_id=query.message.message_thread_id,
                                       text=f"👨‍💻 Owner взял жалобу на рассмотрение.")

        # Уведомление пользователя
        try:
            await context.bot.send_message(
                int(target_uid),
                f"👁 Ваша жалоба взята на рассмотрение."
            )
        except Exception as e:
            logger.info(f"Could not notify user {target_uid} of complaint taken: {e}")

        # Получаем информацию об owner для логов
        agent_username = db.data.get("user_metadata", {}).get(str(OWNER_ID), {}).get("username", "Неизвестно")

        # Лог взятия жалобы
        await send_log(context, "complaint_taken", {
            "user_id": target_uid,
            "agent_username": agent_username,
            "agent_id": str(OWNER_ID),
            "thread_id": thread_id
        })
        return

    # Парсим обычные действия
    parts = data.split("_")
    action = parts[0]

    if action == "close":
        target_uid = parts[1]
        is_complaint = parts[2] == "1" if len(parts) > 2 else False

        agent_num = db.data["agents"][uid_str]["num"] if uid_str in db.data["agents"] else "Owner"

        if is_complaint:
            # Закрытие жалобы
            complaint = db.data["complaints"].get(target_uid)
            if complaint:
                db.data["complaints"][target_uid]["status"] = "closed"
                db.data["active_chats"].pop(target_uid, None)
                db.save()
                await query.message.edit_reply_markup(reply_markup=get_admin_kb(target_uid, True, is_complaint=True))
                await context.bot.close_forum_topic(SUPPORT_CHAT_ID, complaint["thread_id"])
                await context.bot.send_message(SUPPORT_CHAT_ID, message_thread_id=complaint["thread_id"],
                                               text=f"🔴 Owner закрыл жалобу.")

                # Уведомление пользователя
                try:
                    await context.bot.send_message(
                        int(target_uid),
                        f"🔴 Ваша жалоба была закрыта."
                    )
                except Exception as e:
                    logger.info(f"Could not notify user {target_uid} of complaint closure: {e}")

                # Получаем информацию об owner для логов
                agent_db_id = str(OWNER_ID)
                agent_username = db.data.get("user_metadata", {}).get(agent_db_id, {}).get("username", "Неизвестно")

                # Лог закрытия жалобы
                await send_log(context, "complaint_closed", {
                    "user_id": target_uid,
                    "agent_username": agent_username,
                    "agent_id": agent_db_id
                })
        else:
            # Закрытие обычного обращения
            ticket = db.data["tickets"].get(target_uid)
            if ticket:
                db.data["tickets"][target_uid]["status"] = "closed"
                db.data["active_chats"].pop(target_uid, None)
                db.save()
                await query.message.edit_reply_markup(reply_markup=get_admin_kb(target_uid, True))
                await context.bot.close_forum_topic(SUPPORT_CHAT_ID, ticket["thread_id"])
                await context.bot.send_message(SUPPORT_CHAT_ID, message_thread_id=ticket["thread_id"],
                                               text=f"🔴 Агент #{agent_num} закрыл обращение.")

                # Уведомление пользователя о закрытии обращения
                try:
                    await context.bot.send_message(
                        int(target_uid),
                        f"🔴 Ваше обращение было закрыто агентом #{agent_num}."
                    )
                except Exception as e:
                    logger.info(f"Could not notify user {target_uid} of ticket closure: {e}")

                # Получаем информацию об агенте для логов
                agent_db_id = uid_str if uid_str in db.data["agents"] else str(OWNER_ID)
                agent_username = db.data.get("user_metadata", {}).get(agent_db_id, {}).get("username", "Неизвестно")

                # Лог закрытия тикета
                await send_log(context, "ticket_closed", {
                    "user_id": target_uid,
                    "agent_num": agent_num,
                    "agent_username": agent_username,
                    "agent_id": agent_db_id
                })
        return

    target_uid = parts[1]
    agent_num = db.data["agents"][uid_str]["num"] if uid_str in db.data["agents"] else "Owner"

    if action == "take":
        db.data["active_chats"][target_uid] = {"agent_num": agent_num}
        db.save()

        ticket = db.data["tickets"].get(target_uid)
        thread_id = ticket.get("thread_id") if ticket else None

        await query.message.edit_reply_markup(reply_markup=get_admin_kb(target_uid))
        await context.bot.send_message(SUPPORT_CHAT_ID, message_thread_id=query.message.message_thread_id,
                                       text=f"👨‍💻 Агент #{agent_num} взял обращение.")

        # Уведомление пользователя о взятии обращения
        try:
            await context.bot.send_message(
                int(target_uid),
                f"👁 Ваше обращение взято на рассмотрение агентом #{agent_num}."
            )
        except Exception as e:
            logger.info(f"Could not notify user {target_uid} of ticket taken: {e}")

        # Получаем информацию об агенте для логов
        agent_db_id = uid_str if uid_str in db.data["agents"] else str(OWNER_ID)
        agent_username = db.data.get("user_metadata", {}).get(agent_db_id, {}).get("username", "Неизвестно")

        # Лог взятия тикета
        await send_log(context, "ticket_taken", {
            "user_id": target_uid,
            "agent_num": agent_num,
            "agent_username": agent_username,
            "agent_id": agent_db_id,
            "thread_id": thread_id
        })

    elif action == "ban":
        context.user_data.update(
            {'waiting_ban_reason': True, 'ban_target': target_uid, 'ban_msg_id': query.message.message_id})
        await context.bot.send_message(SUPPORT_CHAT_ID, message_thread_id=query.message.message_thread_id,
                                       text="📝 Введите причину бана:")
    elif action == "unban":
        if int(target_uid) in db.data["banned"]:
            db.data["banned"].remove(int(target_uid))
            db.data["ban_reasons"].pop(target_uid, None)
            db.save()

            # Получаем username разблокированного пользователя
            username = db.data.get("user_metadata", {}).get(target_uid, {}).get("username", "Неизвестно")

            # Получаем информацию об агенте для логов
            agent_db_id = uid_str if uid_str in db.data["agents"] else str(OWNER_ID)
            agent_username = db.data.get("user_metadata", {}).get(agent_db_id, {}).get("username", "Неизвестно")

            await query.message.edit_reply_markup(reply_markup=get_admin_kb(target_uid))
            await context.bot.send_message(SUPPORT_CHAT_ID, message_thread_id=query.message.message_thread_id,
                                           text=f"✅ Пользователь разблокирован агентом #{agent_num}.")

            # Уведомление пользователя о разбане
            try:
                await context.bot.send_message(
                    int(target_uid),
                    f"✅ Вы были разблокированы агентом #{agent_num}.\nТеперь вы можете снова обращаться в поддержку."
                )
            except Exception as e:
                logger.info(f"Could not notify user {target_uid} of unban: {e}")

            # Лог разбана
            await send_log(context, "user_unbanned", {
                "user_id": target_uid,
                "username": username,
                "agent_num": agent_num,
                "agent_username": agent_username,
                "agent_id": agent_db_id
            })


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("panel", panel_command, filters=filters.Chat(chat_id=SUPPORT_CHAT_ID)))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_msg))
    app.run_polling()


if __name__ == '__main__':
    main()
