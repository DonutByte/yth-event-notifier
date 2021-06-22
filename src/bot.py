import telegram
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from excel_handler import ExcelWorker
from event import Event
from typing import Union
import logging
import json

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)


class Bot(Updater):
    def __init__(self, bot_token: str, user_info_filepath: str, excel_handler: ExcelWorker, use_context=False,
                 update_interval: Union[list, None] = None):

        if not (isinstance(update_interval, list) or update_interval is None):
            raise TypeError(f'update_interval expected: list or None, got: {type(update_interval).__name__}')
        if update_interval is None:
            self.update_interval = [0, 7, 14]
        else:
            self.update_interval = update_interval

        super().__init__(bot_token, use_context=use_context)
        self.users = self.get_user_info(user_info_filepath)
        self.excel_handler = excel_handler

        self.add_handler(CommandHandler('start', self.start))
        self.add_handler(CommandHandler('help', help))
        self.add_handler(CommandHandler('grade', self.get_grade))
        self.add_handler(CommandHandler('notice', self.set_week))
        self.add_handler(CallbackQueryHandler(self.grade_callback, pattern=r"^\d{1,2}$"))
        self.add_handler(CallbackQueryHandler(self.week_callback, pattern=r"^\d\ddays$"))
        self.add_task(self.get_schedule, interval=30)


    def add_handler(self, handler):
        self.dispatcher.add_handler(handler)

    def add_task(self, task_func, interval):
        self.job_queue.run_repeating(task_func, interval=interval)

    def run(self):
        self.start_polling()
        self.idle()

    @staticmethod
    def get_user_info(filepath) -> dict[int, dict]:
        with open(filepath) as f:
            return json.load(f)

    def start(self, update: Update, context: CallbackContext):
        # check if it's not the first login
        if update.effective_user.id in self.users:
            update.message.reply_text('אתה כבר רשום במערכת, אם אתה רוצה לשנות את זמן ההתראה תשלח השתמש בפקודה /notice')
            return

        user = update.message.from_user
        logger.info("User %s started the conversation.", user.first_name)

        keyboard = [
            [InlineKeyboardButton("ט'", callback_data='9')],
            [InlineKeyboardButton("י'", callback_data='10')],
            [InlineKeyboardButton("יא'", callback_data='11')],
            [InlineKeyboardButton("יב'", callback_data='11')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"שלום {user.first_name}, באיזה כיתה אתה?",
                                 reply_markup=reply_markup)

    def get_grade(self, update: Update, context: CallbackContext):
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text=f'אתה בכיתה {context.user_data.get("grade", "0")}')

    def set_week(self, update: Update, context: CallbackContext):
        if str(update.effective_user.id) not in self.users:
            self.start(update, context)
            return
        try:

            weeks = int(context.args[0])
            if weeks < 1 or weeks > 3:
                update.message.reply_text('הזן מספר בין 1 ל3')
                return

            # update days
            self.users[update.effective_user.id]['days'] = weeks * 7
            update.message.reply_text(f'החל משבוע הבא, תקבל עדכון ל{weeks} שבוע/ות הבא/ים')

        except (IndexError, ValueError):
            update.message.reply_text('שימוש: /notice <מספר שבועות>')

    def grade_callback(self, update: Update, context: CallbackContext):
        query = update.callback_query
        grade = query.data
        context.user_data['grade'] = int(grade)
        logger.info(f'{update.effective_user.first_name} is grade {grade}')

        keyboard = [
            [InlineKeyboardButton('שבוע לפני', callback_data='07days')],
            [InlineKeyboardButton('שבועיים לפני', callback_data='14days')],
            [InlineKeyboardButton('שלושה שבועות לפני', callback_data='21days')],
        ]
        query.edit_message_text("טיל🚀,כמה שבועות לפני תרצה התראה?", reply_markup=InlineKeyboardMarkup(keyboard))

    def week_callback(self, update: Update, context: CallbackContext):
        query = update.callback_query
        days = query.data[:2]
        context.user_data['days'] = int(days)

        logger.info(f'{update.effective_user.full_name} wants a {days} day notice!')

        query.edit_message_text('🔥🔥🔥, הכל מוכן!')

        # store user data
        self.users[update.effective_user.id] = context.user_data
        self.get_schedule(context.bot)

    def get_schedule(self, context: CallbackContext) -> None:
        schedule: dict[int, list[Event]] = self.excel_handler.get_schedule(self.update_interval)

        for user in self.users:
            if 'days' not in self.users[user]:
                continue

            context.bot.send_message(chat_id=user,
                                     text=f"{schedule[self.users[user]['grade']][: self.users[user]['days'] // 7]}")

    def help(self, update: Update, _: CallbackContext):
        update.message.reply_text(HELP_MSG)
