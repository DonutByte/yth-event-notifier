from telegram import ParseMode, ForceReply, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    PicklePersistence,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    ConversationHandler,
    Filters,
    MessageHandler,
)
import telegram
from apscheduler.schedulers.background import BackgroundScheduler
from excel_handler import ExcelWorker
from event import Event
from typing import Union
import logging
import json
import time
from creds import EXCEL_URL

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

START, GRADE, WEEK = range(3)


def catch_errors(func):
    def wrapper(self, *args):
        try:
            return func(self, *args)
        except Exception as e:
            pass
    return wrapper


class Bot(Updater):
    WEEKS_FORMAT = {0: 'שבוע הזה', 1: 'שבוע הבא',
                    2: 'עוד שבועיים', 3: 'עוד שלושה שבועות '}
    MAX_WEEK = 4
    MIN_WEEK = 1
    GRADES = {'ט': 9, 'י': 10, 'יא': 11, 'יב': 12,
              "ט'": 9, "י'": 10, "יא'": 11, "יב'": 12}
    GRADES_KEYBOARD = [["ט'"], ["י'"], ["יא'"], ["יב'"]]
    WEEKS_KEYBOARD = [[f'{i} שבוע/ות']
                      for i in range(MIN_WEEK, MAX_WEEK + 1)] + [['לא ארצה עדכון אוטומטי']]
    OPTIONS = ReplyKeyboardMarkup(keyboard=[['עדכן'], ['שנה כיתה', 'שנה אופק התראה'],
                                            ['עצור עדכון אוטומטי', 'שחזר עדכון אוטומטי'], ['▶️התחל', '❓עזרה']])
    RETURN_OPTION = [['🔙חזור']]
    DETAILS = "\n\n💡 לחיצה על התאריך תשלח אתכם ליומן גוגל\n" \
              rf"ללוח מבחנים המלא: <a href='{EXCEL_URL}'>לחץ כאן</a>"

    # noinspection PyTypeChecker
    def __init__(self, bot_token: str, user_info_filepath: str, excel_path: str, use_context=False,
                 update_interval: Union[list, None] = None):

        assert len(
            self.WEEKS_FORMAT) == self.MAX_WEEK, "WEEKS_FORMAT should match the number of WEEKS"

        if not (isinstance(update_interval, list) or update_interval is None):
            raise TypeError(
                f'update_interval expected: list or None, got: {type(update_interval).__name__}')
        if update_interval is None:
            self.update_interval = [7 * i for i in range(self.MAX_WEEK)]
        else:
            self.update_interval = update_interval

        super().__init__(bot_token, use_context=use_context)
        self.save_users_filepath = user_info_filepath
        self.users = self.get_user_info(user_info_filepath)
        self.excel_handler = ExcelWorker(excel_path, self.update_interval)

        # init command handlers
        start = [CommandHandler('start', self.start), MessageHandler(
            Filters.regex('^▶️התחל$'), self.start)]
        help = [CommandHandler('help', self.help), MessageHandler(
            Filters.regex('^❓עזרה$'), self.help)]
        update = [CommandHandler('update', self.update_one), MessageHandler(
            Filters.regex('^עדכן$'), self.update_one)]
        grade = [CommandHandler('grade', self.change_grade), MessageHandler(Filters.regex('^שנה כיתה$'),
                                                                            self.change_grade)]
        week = [CommandHandler('notice', self.change_week), MessageHandler(Filters.regex('^שנה אופק התראה$'),
                                                                           self.change_week)]
        stop = [CommandHandler('stop', self.stop_updating_me), MessageHandler(Filters.regex('^עצור עדכון אוטומטי$'),
                                                                              self.stop_updating_me)]
        restart = [CommandHandler('restart', self.start_updating_me),
                   MessageHandler(Filters.regex('^שחזר עדכון אוטומטי$'), self.start_updating_me)]
        cancel = [CommandHandler('cancel', self.cancel), MessageHandler(
            Filters.regex('^🔙חזור$'), self.cancel)]

        setup_handler = ConversationHandler(
            entry_points=start,
            states={
                START: start,
                GRADE: [MessageHandler(Filters.regex('|'.join(self.GRADES)), self.grade), MessageHandler(Filters.text, self.unknown_message(ReplyKeyboardMarkup(self.GRADES_KEYBOARD)))],
                WEEK: [MessageHandler(Filters.regex(f'[{self.MIN_WEEK}-{self.MAX_WEEK}] שבוע/ות') ^ Filters.regex(
                    '^לא ארצה עדכון אוטומטי$'), self.week), MessageHandler(Filters.text, self.unknown_message(ReplyKeyboardMarkup(self.WEEKS_KEYBOARD)))],
            },
            fallbacks=[CommandHandler('cancel', self.start)],
        )

        change_grade_handler = ConversationHandler(
            entry_points=grade,
            states={
                START: grade,
                GRADE: [MessageHandler(Filters.regex('|'.join(self.GRADES)), self.grade_callback)],
            },
            fallbacks=cancel
        )

        change_notice_handler = ConversationHandler(
            entry_points=week,
            states={
                START: week,
                WEEK: [MessageHandler(Filters.regex(f'[{self.MIN_WEEK}-{self.MAX_WEEK}] שבוע/ות|לא ארצה עדכון אוטומטי'),
                                      self.week)],
            },
            fallbacks=cancel
        )

        self.add_handler(setup_handler)
        self.add_handler(change_grade_handler)
        self.add_handler(change_notice_handler)
        self.add_handler(help)
        self.add_handler(stop)
        self.add_handler(restart)
        self.add_handler(update)

        self.add_handler(MessageHandler(
            Filters.text, self.unknown_message(self.OPTIONS)))

        # update_all scheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(lambda: self.update_all(
            self.bot), trigger='cron', day_of_week='sun', hour='7', minute='00')
        scheduler.start()

    def add_handler(self, handler):
        if isinstance(handler, (list, tuple)):
            for item in handler:
                self.dispatcher.add_handler(item)
        else:
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
            json.dump(self.users, f, indent=4)

    def start(self, update: Update, context: CallbackContext):
        # check if it's not the first login
        if str(update.effective_user.id) in self.users:
            update.message.reply_text('אתה כבר רשום במערכת\n'
                                      f'תוכל לשנות/לראות נתונים ע"י לחיצה על הכפתור המתאים👇',
                                      reply_markup=self.OPTIONS)
            return

        user = update.message.from_user
        logger.info("User %s started the conversation.", user.first_name)

        context.bot.send_message(chat_id=update.effective_chat.id, text=f"שלום {user.first_name}, באיזה כיתה אתה?",
                                 reply_markup=ReplyKeyboardMarkup(self.GRADES_KEYBOARD,
                                                                  one_time_keyboard=True,
                                                                  input_field_placeholder='באיתה כיתה אתה?'))
        return GRADE

    def stop_updating_me(self, update: Update, _: CallbackContext):
        if str(update.effective_user.id) not in self.users:
            update.message.reply_text('עליך קודם להירשם!\nלחץ ▶️התחל')
        else:
            self.users[str(update.effective_user.id)]['wantsUpdate'] = False
            update.message.reply_text(
                "😔 לא תקבל עוד עדכונים...\nאם תתחרט לחץ 'שחזר עדכון אוטומטי'")
            self.save_user_info()

    def start_updating_me(self, update: Update, _: CallbackContext):
        if str(update.effective_user.id) not in self.users:
            update.message.reply_text('עליך קודם להירשם!\nלחץ ▶️התחל')
        else:
            self.users[str(update.effective_user.id)]['wantsUpdate'] = True
            update.message.reply_text(
                "משבוע הבא תקבל עדכונים אוטומטים!\nכדי להפסיק לחץ 'עצור עדכון אוטומטי'")
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
            context.user_data['days'] = 7
            context.user_data['wantsUpdate'] = False
            self.users[user] = context.user_data
            update.message.reply_text("לא תקבל עדכונים שבועיים אך תמיד תוכל לבקש ידנית: /update או 'עדכן'",
                                      reply_markup=self.OPTIONS)
            self.save_user_info()
        else:

            try:
                weeks = int(update.message.text.replace(' שבוע/ות', ''))
                if weeks < self.MIN_WEEK or weeks > self.MAX_WEEK:
                    update.message.reply_text(
                        f'הזן מספר בין {self.MIN_WEEK} ל{self.MAX_WEEK}')
                    return WEEK

                # update days
                context.user_data['wantsUpdate'] = True
                context.user_data['days'] = weeks * 7

                if user in self.users:
                    self.users[user]['wantsUpdate'] = context.user_data['wantsUpdate']
                    self.users[user]['days'] = context.user_data['days']
                else:
                    self.users[user] = context.user_data

                update.message.reply_text(f'החל משבוע הבא, תקבל עדכון ל{weeks} שבוע/ות הבא/ים',
                                          reply_markup=self.OPTIONS)
                self.save_user_info()

            except (IndexError, ValueError):
                if self.users[user]["wantsUpdate"]:
                    update.message.reply_text(
                        f'אתה מקבל התראה של *__{self.users[user]["days"] // 7} שבוע/ות__*\n'
                        "כדי לשנות: /notice או 'שנה אופק התראה'", parse_mode=ParseMode.MARKDOWN_V2,
                        reply_markup=self.OPTIONS)
                else:
                    update.message.reply_text("**אינך מקבל התרעות אוטומטיות**\n"
                                              "כדי לקבל: /restart או 'שחזר עדכון אוטומטי'",
                                              parse_mode=ParseMode.MARKDOWN_V2, reply_markup=self.OPTIONS)

        return ConversationHandler.END

    def change_grade(self, update: Update, _: CallbackContext):
        user = str(update.effective_user.id)
        if user not in self.users:
            update.message.reply_text('כדי לשנות כיתה עליך קודם להירשם...')
            return ConversationHandler.END
        grade = next((text for text, num in self.GRADES.items()
                     if num == self.users[user]["grade"]), "שלא קיימת")
        update.message.reply_text(f'אתה __בכיתה {grade}__'
                                  f'\nאם אתה רוצה לשנות כיתה, בחר את הכיתה החדשה:\n'
                                  f"אם לא לחץ '{self.RETURN_OPTION[0][0]}'",
                                  parse_mode=ParseMode.MARKDOWN_V2,
                                  reply_markup=ReplyKeyboardMarkup(self.GRADES_KEYBOARD + self.RETURN_OPTION,
                                                                   input_field_placeholder='באיתה כיתה אתה?'))
        return GRADE

    def change_week(self, update: Update, _: CallbackContext):
        user = str(update.effective_user.id)
        if self.users[user]["wantsUpdate"]:
            current_grade_msg = f'אתה מקבל התראה של *__{self.users[user]["days"] // 7} שבוע/ות__*'
        else:
            current_grade_msg = "**אינך מקבל התרעות אוטומטיות**"
        update.message.reply_text(f'{current_grade_msg}\nאם אתה רוצה לשנות בחר אופציה חדשה\n'
                                  f"אם לא לחץ '{self.RETURN_OPTION[0][0]}'",
                                  reply_markup=ReplyKeyboardMarkup(self.WEEKS_KEYBOARD + self.RETURN_OPTION,
                                                                   input_field_placeholder='באיתה כיתה אתה?'),
                                  parse_mode=ParseMode.MARKDOWN_V2)
        return WEEK

    def cancel(self, update: Update, _: CallbackContext):
        update.message.reply_text(
            'אני עדיין פה אם תצטרך!', reply_markup=self.OPTIONS)
        return ConversationHandler.END

    def unknown_message(self, keyboard):
        def wrapper(update: Update, _: CallbackContext):
            update.message.reply_text(f"לא הבנתי\nבבקשה תשתמש בכפתורים\n",
                                      parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboard)
        return wrapper

    def grade_callback(self, update: Update, context: CallbackContext):
        grade = update.message.text
        try:
            context.user_data['grade'] = int(self.GRADES[grade])
        except KeyError:
            update.message.reply_text(f"כיתה שבחרת לא קיימת\nאם לא תרצה לשנות לחץ '{self.RETURN_OPTION[0][0]}'",
                                      reply_markup=ReplyKeyboardMarkup(self.GRADES_KEYBOARD + self.RETURN_OPTION,
                                                                       one_time_keyboard=True,
                                                                       input_field_placeholder='בחר כיתה'))
            return GRADE
        else:
            user = str(update.effective_user.id)
            if user in self.users:
                update.message.reply_text(
                    'הכיתה שונתה בהצלחה!', reply_markup=self.OPTIONS)
                self.users[user]['grade'] = context.user_data['grade']
                self.save_user_info()
        return ConversationHandler.END

    @catch_errors
    def update_all(self, bot: telegram.Bot) -> None:
        schedule: dict[int, list[list[Event]]
                       ] = self.excel_handler.get_schedule(self.update_interval)
        for user in self.users:
            if 'days' not in self.users[user] or not self.users[user]['wantsUpdate']:
                continue

            message = self.format_schedule(schedule[self.users[user]['grade']][: self.users[user]['days'] // 7]) \
                + self.DETAILS
            try:
                bot.send_message(chat_id=user, text=message, parse_mode=ParseMode.HTML,
                                 disable_web_page_preview=True, reply_markup=self.OPTIONS)
            except Exception:
                print(f'Failed to update {user}')
                continue
            time.sleep(1)

    @catch_errors
    def update_one(self, update: Update, context: CallbackContext):
        user = str(update.effective_user.id)
        if user not in self.users:
            update.message.reply_text('עליך קודם להירשם\nלחץ \start')
            return

        try:
            schedule: dict[int, list[list[Event]]] = self.excel_handler.get_schedule(
                self.update_interval)
        except RuntimeError as e:
            update.message.reply_text(text=str(e))
        else:
            message = self.format_schedule(schedule[self.users[user]['grade']][: self.users[user]['days'] // 7]) \
                + self.DETAILS

            context.bot.send_message(chat_id=user, text=message, parse_mode=ParseMode.HTML,
                                     disable_web_page_preview=True, reply_markup=self.OPTIONS)

    def help(self, update: Update, _: CallbackContext):
        help_message = ''
        for idx, command in enumerate(_.bot.get_my_commands()):
            help_message += f'{chr(ord("א") + idx)}. /{command.command} - {command.description}\n'
        help_message += '\n\n' + 'לשאלות נוספות אנא פנו ל<a href="t.me/Da_Donut">מנהל הבוט</a>'
        update.message.reply_text(help_message, reply_markup=self.OPTIONS,
                                  parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    def format_schedule(self, schedule: list[list[Event]]):
        msg = ''
        for i, week in enumerate(schedule):
            msg += f'<u><b>{self.WEEKS_FORMAT[i]}</b></u>\n'

            # only notice the weeks where there are event
            if len(week) == 0:
                msg += "<b>אין אירועים</b>😁"

            for event in week:
                msg += f'{event: <10|%d/%m/%y}\n'
            msg += '\n'
        return msg
