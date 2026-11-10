import asyncio
import logging
import os
import sqlite3

from telegram import (
    BotCommand,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app import app as flask_app
from db import get_db


logger = logging.getLogger(__name__)

# 四个录入阶段。
COMPANY, CONTACT, PRODUCT, CONFIRM = range(4)

# 处理私聊中的文字消息。
PRIVATE = filters.ChatType.PRIVATE
TEXT = PRIVATE & filters.TEXT & ~filters.COMMAND


def save_lead(lead):
    """使用 Flask 的数据库配置保存线索。"""
    with flask_app.app_context():
        with get_db() as connection:
            cursor = connection.execute(
                """
                INSERT INTO leads (company, contact, product, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    lead["company"],
                    lead["contact"],
                    lead["product"],
                    "pending",
                ),
            )
            lead_id = cursor.lastrowid

        return lead_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示使用说明。"""
    await update.message.reply_text(
        "欢迎使用展会客户跟进助手。\n\n"
        "/new 新增客户线索\n"
        "/cancel 取消当前录入\n"
        "/help 查看使用说明"
    )


async def begin_lead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """为当前用户创建草稿，开始录入。"""
    context.user_data["lead_draft"] = {}

    await update.message.reply_text(
        "请发送公司名称，最多 200 个字符。\n"
        "随时发送 /cancel 可以取消。",
        reply_markup=ReplyKeyboardRemove(),
    )

    return COMPANY


async def read_text(update, label, limit):
    """校验文字是否为空、是否超过长度限制。"""
    value = update.message.text.strip()

    if not value:
        await update.message.reply_text(
            f"{label}不能为空，请重新发送。"
        )
        return None

    if len(value) > limit:
        await update.message.reply_text(
            f"{label}最多填写 {limit} 个字符，请重新发送。"
        )
        return None

    return value


async def receive_company(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """保存公司名称，然后询问联系人。"""
    value = await read_text(update, "公司名称", 200)

    if value is None:
        return COMPANY

    context.user_data["lead_draft"]["company"] = value

    await update.message.reply_text(
        "请发送联系人，最多 200 个字符。"
    )

    return CONTACT


async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """保存联系人，然后询问产品需求。"""
    value = await read_text(update, "联系人", 200)

    if value is None:
        return CONTACT

    context.user_data["lead_draft"]["contact"] = value

    await update.message.reply_text(
        "请发送产品需求，最多 2000 个字符。"
    )

    return PRODUCT


async def receive_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """保存产品需求，并显示确认信息。"""
    value = await read_text(update, "产品需求", 2000)

    if value is None:
        return PRODUCT

    lead = context.user_data["lead_draft"]
    lead["product"] = value

    await update.message.reply_text(
        "请核对客户信息。\n\n"
        f"公司名称：{lead['company']}\n"
        f"联系人：{lead['contact']}\n"
        "初始状态：待联系\n\n"
        "产品需求见下一条。"
    )

    # 产品需求单独发送，避免较长内容超过消息长度限制。
    await update.message.reply_text(
        f"产品需求\n{lead['product']}",
        reply_markup=ReplyKeyboardMarkup(
            [["确认保存", "取消录入"]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

    return CONFIRM


async def confirm_lead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """确认后写入数据库。"""
    text = update.message.text.strip()

    if text == "取消录入":
        return await cancel(update, context)

    if text != "确认保存":
        await update.message.reply_text(
            "请点击“确认保存”，或发送 /cancel 取消。"
        )
        return CONFIRM

    lead = context.user_data["lead_draft"]
    lead_id = lead.get("saved_id")

    if lead_id is None:
        try:
            # 在线程中执行同步数据库操作。
            lead_id = await asyncio.to_thread(
                save_lead,
                dict(lead),
            )
        except sqlite3.Error:
            logger.exception("保存客户线索失败")

            await update.message.reply_text(
                "保存失败，请稍后再次发送“确认保存”，"
                "或发送 /cancel 取消。"
            )
            return CONFIRM

        # 先记住保存结果，避免回复失败后重试时重复写入。
        lead["saved_id"] = lead_id

    await update.message.reply_text(
        f"客户线索已保存，编号为 {lead_id}，状态为待联系。\n"
        "刷新网页即可查看。发送 /new 可以继续录入。",
        reply_markup=ReplyKeyboardRemove(),
    )

    context.user_data.pop("lead_draft", None)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """结束当前用户的录入，清理对应草稿。"""
    lead = context.user_data.pop("lead_draft", {})

    if lead.get("saved_id") is not None:
        text = (
            f"编号 {lead['saved_id']} 的线索已保存，"
            "可在网页中查看。"
        )
    else:
        text = "已取消录入。发送 /new 可以重新开始。"

    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardRemove(),
    )

    return ConversationHandler.END


async def reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理暂时无法识别的消息。"""
    await update.message.reply_text(
        "请按提示发送文字。"
        "发送 /new 开始录入，或发送 /cancel 取消。"
    )


async def set_commands(application):
    """设置 Telegram 中的命令菜单。"""
    await application.bot.set_my_commands(
        [
            BotCommand("start", "查看使用说明"),
            BotCommand("new", "新增客户线索"),
            BotCommand("cancel", "取消当前录入"),
            BotCommand("help", "查看使用说明"),
        ]
    )


async def on_error(update, context):
    """记录错误，并尽可能向用户提示。"""
    logger.error(
        "处理失败，错误类型为 %s",
        type(context.error).__name__,
    )

    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text(
                "处理出现错误，请发送 /new 重新开始。"
                "已保存的线索可在网页中查看。"
            )
        except TelegramError:
            logger.warning("暂时无法向 Telegram 回复消息")


def build_application(token):
    """创建 Bot 并注册命令和对话流程。"""
    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(False)
        .post_init(set_commands)
        .build()
    )

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("new", begin_lead, filters=PRIVATE),
        ],
        states={
            COMPANY: [
                MessageHandler(TEXT, receive_company),
            ],
            CONTACT: [
                MessageHandler(TEXT, receive_contact),
            ],
            PRODUCT: [
                MessageHandler(TEXT, receive_product),
            ],
            CONFIRM: [
                MessageHandler(TEXT, confirm_lead),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel, filters=PRIVATE),
            CommandHandler(
                ["start", "help"],
                start,
                filters=PRIVATE,
            ),
            MessageHandler(PRIVATE, reminder),
        ],
        allow_reentry=True,
        per_chat=True,
        per_user=True,
    )

    application.add_handler(conversation)

    application.add_handler(
        CommandHandler(
            ["start", "help"],
            start,
            filters=PRIVATE,
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel,
            filters=PRIVATE,
        )
    )

    application.add_handler(
        MessageHandler(PRIVATE, reminder)
    )

    application.add_error_handler(on_error)

    return application


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    if not token:
        raise RuntimeError(
            "请在 .env 中设置 TELEGRAM_BOT_TOKEN。"
        )

    # 启动前检查数据库是否已经初始化。
    try:
        with flask_app.app_context():
            get_db().execute(
                """
                SELECT company, contact, product, status
                FROM leads
                LIMIT 1
                """
            )
    except sqlite3.Error as error:
        raise RuntimeError(
            "请先运行 python -m flask --app app init-db "
            "初始化数据库。"
        ) from error

    application = build_application(token)

    logger.info(
        "Bot 启动，数据库为 %s",
        flask_app.config["DATABASE"],
    )

    application.run_polling(
        allowed_updates=["message"],
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )

    # HTTP 请求地址包含 Bot Token，关闭常规请求日志。
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    main()