from telegram import ParseMode, ForceReply, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    ConversationHandler,
    Filters,
    MessageHandler,
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from apscheduler.schedulers.background import BackgroundScheduler
from excel_handler import ExcelWorker
from event import Event
from typing import Union
import logging
import json
from creds import EXCEL_URL

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

START, GRADE, WEEK = range(3)


class Bot(Updater):
    MAX_WEEK = 3
    MIN_WEEK = 1
    GRADES = {'ט': 9, 'י': 10, 'יא': 11, 'יב': 12,
              "ט'": 9, "י'": 10, "יא'": 11, "יב'": 12}
    GRADES_KEYBOARD = [["ט'"], ["י'"], ["יא'"], ["יב'"]]
    WEEKS_KEYBOARD = [[f'{i} שבוע/ות'] for i in range(MIN_WEEK, MAX_WEEK + 1)] + [['לא ארצה עדכון אוטומטי']]
    DETAILS = "\n\n💡 לחיצה על התאריך תשלח אותכם ליומן גוגל\n" \
              rf"ללוח מבחנים המלא: [לחץ כאן]({EXCEL_URL})"
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

        setup_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                START: [CommandHandler('start', self.start)],
                GRADE: [MessageHandler(Filters.regex('|'.join(self.GRADES)), self.grade)],
                WEEK: [MessageHandler(Filters.regex(f'[{self.MIN_WEEK}-{self.MAX_WEEK}] שבוע/ות') ^ Filters.regex('^לא ארצה עדכון אוטומטי$'), self.week)],
            },
            fallbacks=[CommandHandler('cancel', self.start)],
        )

        change_grade_handler = ConversationHandler(
            entry_points=[CommandHandler('grade', self.change_grade),
                          MessageHandler(Filters.regex('שנה כיתה'), self.change_grade)],
            states={
                START: [CommandHandler('grade', self.change_grade)],
                GRADE: [MessageHandler(Filters.regex('|'.join(self.GRADES)), self.grade_callback)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel) , setup_handler,
                       CommandHandler('help', self.help), CommandHandler('stop', self.stop_updating_me),
                       CommandHandler('update', self.update_one)]
        )

        change_notice_handler = ConversationHandler(
            entry_points=[CommandHandler('notice', self.change_week),
                          MessageHandler(Filters.regex('שנה התראה'), self.change_week)],
            states={
                START: [CommandHandler('notice', self.change_week),
                        MessageHandler(Filters.regex('שנה התראה'), self.change_week)],
                WEEK: [MessageHandler(Filters.regex(f'[{self.MIN_WEEK}-{self.MAX_WEEK}] שבוע/ות'), self.week)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel), setup_handler, change_grade_handler,
                       CommandHandler('help', self.help), CommandHandler('stop', self.stop_updating_me),
                       CommandHandler('update', self.update_one)]
        )

        self.add_handler(setup_handler)
        self.add_handler(change_grade_handler)
        self.add_handler(change_notice_handler)
        self.add_handler(CommandHandler('help', self.help))
        self.add_handler(CommandHandler('stop', self.stop_updating_me))
        self.add_handler(CommandHandler('update', self.update_one))

        self.add_handler(CallbackQueryHandler(self.grade_callback, pattern=r"^\d{1,2}$"))
        self.add_handler(CallbackQueryHandler(self.week_callback, pattern=r"^\d\ddays$"))

        scheduler = BackgroundScheduler()
        scheduler.add_job(lambda: self.update_all(self.bot), trigger='cron', day_of_week='wed', hour='07', minute='00')
        scheduler.start()

        # self.add_task(self.update_all, interval=30)

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

        context.bot.send_message(chat_id=update.effective_chat.id, text=f"שלום {user.first_name}, באיזה כיתה אתה?",
                                 reply_markup=ReplyKeyboardMarkup(self.GRADES_KEYBOARD, one_time_keyboard=True,
                                                                  input_field_placeholder='באיתה כיתה אתה?'))
        return GRADE

    def stop_updating_me(self, update: Update, context: CallbackContext):
        if str(update.effective_user.id) not in self.users:
            update.message.reply_text('עליך קודם להירשם')
            self.start(update, context)

        else:
            del self.users[str(update.effective_user.id)]
            update.message.reply_text('😔 לא תקבל עוד עדכונים...\nאם תתחרט אני פה 😃')
            self.save_user_info()

    def grade(self, update: Update, context: CallbackContext):
        result = self.grade_callback(update, context)
        if result == GRADE:
            return GRADE
        else:
            update.message.reply_text(text=f'{update.effective_user.full_name} אתה בכיתה {update.message.text}!'
                                           f'\nדבר אחרון, כמה שבועות לפני תרצה התראה?',
                                      reply_markup=ReplyKeyboardMarkup(self.WEEKS_KEYBOARD, one_time_keyboard=True,
                                                                       input_field_placeholder='כמה שבועות לפני תרצה התראה?'))
            return WEEK

    def week(self, update: Update, context: CallbackContext):
        user = str(update.effective_user.id)
        if update.message.text == 'לא ארצה עדכון אוטומטי':
            context.user_data['days'] = -1
            context.user_data['wantsUpdate'] = False
            update.message.reply_text('לא תקבל עדכונים שבועיים אך תמיד תוכל לבקש ידנית: /update',
                                      reply_markup=ReplyKeyboardRemove())
            self.users[user] = context.user_data
            self.save_user_info()
        else:

            try:
                weeks = int(update.message.text.replace(' שבוע/ות', ''))
                if weeks < self.MIN_WEEK or weeks > self.MAX_WEEK:
                    update.message.reply_text(f'הזן מספר בין {self.MIN_WEEK} ל{self.MAX_WEEK}')
                    return ConversationHandler.END

                # update days
                context.user_data['wantsUpdate'] = True
                context.user_data['days'] = weeks * 7

                if user in self.users:
                    self.users[user]['wantsUpdate'] = context.user_data['']
                    self.users[user]['days'] = context.user_data['days']
                else:
                    self.users[user] = context.user_data

                update.message.reply_text(f'החל משבוע הבא, תקבל עדכון ל{weeks} שבוע/ות הבא/ים',
                                          reply_markup=ReplyKeyboardRemove())
                self.save_user_info()

            except (IndexError, ValueError):
                if self.users[user]["wantsUpdate"]:
                    update.message.reply_text(
                        f'אתה מקבל התראה של *__{self.users[user]["days"] // 7} שבוע/ות__*\n'
                        r'כדי לשנות: /notice \<מספר שבועות\>', parse_mode=ParseMode.MARKDOWN_V2)
                else:
                    update.message.reply_text("**אינך מקבל התרעות אוטומטיות**\n"
                                              r"כדי לקבל: /notice \<מספר שבועות\>", parse_mode=ParseMode.MARKDOWN_V2)

        return ConversationHandler.END

    def change_grade(self, update: Update, _: CallbackContext):
        user = str(update.effective_user.id)
        if user not in self.users:
            update.message.reply_text('כדי לשנות כיתה עליך קודם להירשם...')
            return ConversationHandler.END
        grade = next((text for text, num in self.GRADES.items() if num == self.users[user]["grade"]), "שלא קיימת")
        update.message.reply_text(f'אתה __בכיתה {grade}__'
                                  f'\nאם אתה רוצה לשנות כיתה, בחר את הכיתה החדשה:\n'
                                  f'אם לא לחץ /cancel',
                                  parse_mode=ParseMode.MARKDOWN_V2,
                                  reply_markup=ReplyKeyboardMarkup(self.GRADES_KEYBOARD, one_time_keyboard=True,
                                                                   input_field_placeholder='באיתה כיתה אתה?'))
        return GRADE

    def change_week(self, update: Update, _: CallbackContext):
        user = str(update.effective_user.id)
        if self.users[user]["wantsUpdate"]:
            update.message.reply_text(
                f'אתה מקבל התראה של *__{self.users[user]["days"] // 7} שבוע/ות__*\n', parse_mode=ParseMode.MARKDOWN_V2)
        else:
            update.message.reply_text("**אינך מקבל התרעות אוטומטיות**\n", parse_mode=ParseMode.MARKDOWN_V2)
        update.message.reply_text('אם אתה רוצה לשנות בחר אופציה חדשה\nאם לא לחץ /cancel',
                                  reply_markup=ReplyKeyboardMarkup(self.WEEKS_KEYBOARD, one_time_keyboard=True,
                                                                   input_field_placeholder='באיתה כיתה אתה?'))
        return WEEK

    @staticmethod
    def cancel(update: Update, _: CallbackContext):
        update.message.reply_text('אני עדיין פה אם תצטרך!', reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    def grade_callback(self, update: Update, context: CallbackContext):
        grade = update.message.text
        try:
            context.user_data['grade'] = int(self.GRADES[grade])
        except KeyError:
            update.message.reply_text(f'הכיתה שבחרת לא קיימת\nבחר אחת מאלו: {", ".join(self.GRADES.keys())}',
                                      reply_markup=ForceReply())
            return GRADE
        else:
            user = str(update.effective_user.id)
            if user in self.users:
                update.message.reply_text('הכיתה שונתה בהצלחה!')
                self.users[user]['grade'] = context.user_data['grade']
                self.save_user_info()
        return ConversationHandler.END

    def week_callback(self, update: Update, context: CallbackContext):
        query = update.callback_query
        days = query.data[:2]
        context.user_data['days'] = int(days)

        logger.info(f'{update.effective_user.full_name} wants a {days} day notice!')

        query.edit_message_text('🔥🔥🔥, הכל מוכן!')

        # store user data
        self.users[str(update.effective_user.id)] = context.user_data
        self.save_user_info()
        self.update_all(context.bot)

    def update_all(self, context) -> None:
        print(f'Updating users: {self.users}')
        schedule: dict[int, list[list[Event]]] = self.excel_handler.get_schedule(self.update_interval)
        print(f'{schedule}')
        for user in self.users:
            if 'days' not in self.users[user]:
                continue

            context.bot.send_message(chat_id=user,
                                     text="\n".join(f"{event: <10|%x}" for events in
                                                    schedule[self.users[user]['grade']][: self.users[user]['days'] // 7]
                                                    for event in events) + self.DETAILS,
                                     parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

    def update_one(self, update: Update, context: CallbackContext):
        user = str(update.effective_user.id)
        try:
            schedule: dict[int, list[list[Event]]] = self.excel_handler.get_schedule(self.update_interval)
        except RuntimeError as e:
            update.message.reply_text(text=str(e))
        else:
            context.bot.send_message(chat_id=user,
                                     text="\n".join(f"{event: <10|%x}" for events in
                                                    schedule[self.users[user]['grade']][: self.users[user]['days'] // 7]
                                                    for event in events) + self.DETAILS,
                                     parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

    def help(self, update: Update, _: CallbackContext):
        update.message.reply_text(self.HELP_MSG)
