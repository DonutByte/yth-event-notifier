import telegram
from telegram import ParseMode
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
    DETAILS = "\n💡 לחיצה על התאריך תשלח אותכם ליומן גוגל\n" \
              "ללוח מבחנים המלא: [https://docs\.google.com/spreadsheets/d/13ltt-Kp7BtnSfmaQECrIwSSjcP7x4OrfP85tse9C2sM/edit#gid=1102623273](לחץ כאן)"
    MAX_WEEK = 3
    MIN_WEEK = 1
    HELP_MSG = """הנה הדברים שאני יודע  לעשות:
    א. /start - להצטרף לקבלת ההתראות
    ב. /notice - תשנה או תזכיר לכם את זמן ההתראה שלכם
    ג. /stop -  יעצור את הבוט מלשלוח לכם התראות, כדי לקבל שוב עליכם להתצטרף שוב (ראו א.)
    ד. /help - ההודעה הזו"""

    def __init__(self, bot_token: str, user_info_filepath: str, excel_handler: ExcelWorker, use_context=False,
                 update_interval: Union[list, None] = None):

        if not (isinstance(update_interval, list) or update_interval is None):
            raise TypeError(f'update_interval expected: list or None, got: {type(update_interval).__name__}')
        if update_interval is None:
            self.update_interval = [0, 7, 14]
        else:
            self.update_interval = update_interval

        super().__init__(bot_token, use_context=use_context)
        self.save_users_filepath = user_info_filepath
        self.users = self.get_user_info(user_info_filepath)
        self.excel_handler = excel_handler

        self.add_handler(CommandHandler('start', self.start))
        self.add_handler(CommandHandler('help', self.help))
        self.add_handler(CommandHandler('grade', self.get_grade))
        self.add_handler(CommandHandler('notice', self.set_week))
        self.add_handler(CallbackQueryHandler(self.grade_callback, pattern=r"^\d{1,2}$"))
        self.add_handler(CallbackQueryHandler(self.week_callback, pattern=r"^\d\ddays$"))
        self.add_handler(CommandHandler('stop', self.stop_updating_me))

        self.add_task(self.get_schedule, interval=30)

    def add_handler(self, handler):
        self.dispatcher.add_handler(handler)

    def add_task(self, task_func, interval):
        self.job_queue.run_repeating(task_func, interval=interval)

    def run(self):
        self.start_polling()
        self.idle()

    @staticmethod
    def get_user_info(filepath) -> dict[str, dict]:
        with open(filepath) as f:
            return json.load(f)

    def save_user_info(self):
        with open(self.save_users_filepath, 'w') as f:
            json.dump(self.users, f)

    def start(self, update: Update, context: CallbackContext):
        # check if it's not the first login
        if str(update.effective_user.id) in self.users:
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

    def stop_updating_me(self, update: Update, context: CallbackContext):
        if str(update.effective_user.id) not in self.users:
            update.message.reply_text('עליך קודם להירשם')
            self.start(update, context)

        else:
            del self.users[str(update.effective_user.id)]
            update.message.reply_text('😔 לא תקבל עוד עדכונים...\nאם תתחרט אני פה 😃')

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
            self.users[str(update.effective_user.id)]['days'] = weeks * 7
            update.message.reply_text(f'החל משבוע הבא, תקבל עדכון ל{weeks} שבוע/ות הבא/ים')

        except (IndexError, ValueError):
            update.message.reply_text(
                f'אתה מקבל התראה של *__{self.users[str(update.effective_user.id)]["days"] // 7} שבוע/ות__*\n'
                r'כדי לשנות: /notice \<מספר שבועות\>', parse_mode=ParseMode.MARKDOWN_V2)

    def grade_callback(self, update: Update, context: CallbackContext):
        query = update.callback_query
        grade = query.data
        context.user_data['grade'] = int(grade)
        logger.info(f'{update.effective_user.first_name} is grade {grade}')

        keyboard = [[InlineKeyboardButton(f'{i} שבוע/ות לפני', callback_data=f'{i * 7:02}days')] for i in
                    range(self.MIN_WEEK, self.MAX_WEEK + 1)]
        query.edit_message_text("טיל🚀,כמה שבועות לפני תרצה התראה?", reply_markup=InlineKeyboardMarkup(keyboard))

    def week_callback(self, update: Update, context: CallbackContext):
        query = update.callback_query
        days = query.data[:2]
        context.user_data['days'] = int(days)

        logger.info(f'{update.effective_user.full_name} wants a {days} day notice!')

        query.edit_message_text('🔥🔥🔥, הכל מוכן!')

        # store user data
        self.users[str(update.effective_user.id)] = context.user_data
        self.save_user_info()
        self.get_schedule(context.bot)

    def get_schedule(self, context: CallbackContext) -> None:
        schedule: dict[int, list[Event]] = self.excel_handler.get_schedule(self.update_interval)
        for user in self.users:
            if 'days' not in self.users[user]:
                continue

            context.bot.send_message(chat_id=user,
                                     text="\n".join(f"{event: <10|%x}" for events in
                                                    schedule[self.users[user]['grade']][: self.users[user]['days'] // 7]
                                                    for event in events),
                                     parse_mode=ParseMode.MARKDOWN_V2)

    def help(self, update: Update, _: CallbackContext):
        update.message.reply_text(self.HELP_MSG)
